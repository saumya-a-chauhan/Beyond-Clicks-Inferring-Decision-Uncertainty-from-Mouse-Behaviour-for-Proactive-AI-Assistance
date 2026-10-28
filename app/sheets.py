"""Results sheets: one row per participant x shopping round, as Excel (Pilot + Main sheets) or CSV.

The same columns are used for download and upload, so a sheet downloaded on one laptop can be uploaded on another
and is shown (and re-downloaded) together with that laptop's own data.
"""
import csv
import io
import json
import socket
import statistics as st
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select

from . import db
from .analysis import TLX_KEYS, sus_score
from .defaults import CONDITIONS

STUDIES = ("pilot", "main")
SHEET_NAMES = {"pilot": "Pilot", "main": "Main"}

# (column, meaning) - the order here is the order in the sheet
COLUMNS = [
    ("site", "Laptop that collected the data (Settings > Laptop name)"),
    ("participant", "Participant code (P01 = pilot, M01 = main)"),
    ("study", "pilot or main"),
    ("status", "completed / started / declined"),
    ("excluded", "TRUE if a researcher excluded this person"),
    ("simulated", "TRUE for fake test data"),
    ("date", "Date of the session (YYYY-MM-DD)"),
    ("round", "Shopping round number (1-4; 5 = pilot AI check)"),
    ("task_key", "Internal round id (t1-t4, ai)"),
    ("condition", "C1 No AI, C2 Ask AI, C3 Smart pop-up, C4 Random pop-up"),
    ("condition_name", "Condition in words"),
    ("phone_set", "Phone set used (S1-S5)"),
    ("decision_time_s", "Seconds from round start to clicking Choose"),
    ("chosen_phone", "Phone chosen first"),
    ("correct", "TRUE if the first choice was the correct phone"),
    ("rank", "Rank of first choice: 1 correct, 2 main trap, 3 second trap, 4 dominated"),
    ("switched", "TRUE if they changed their choice in the switch test"),
    ("final_choice", "Phone after the switch test"),
    ("final_correct", "TRUE if the final choice was correct"),
    ("final_rank", "Rank of the final choice"),
    ("popups_shown", "Number of AI pop-ups shown"),
    ("unsure_yes", "Pop-ups answered 'yes, I was unsure'"),
    ("unsure_no", "Pop-ups answered 'no'"),
    ("help_accepted", "Pop-ups where Compare or Explain was clicked"),
    ("help_dismissed", "Pop-ups closed with 'No thanks'"),
    ("ai_requests", "AI answers given (pop-up help + Ask AI)"),
    ("unsure_moments_marked", "Pilot replay: number of 'I was unsure' moments marked"),
    ("confidence", "Confidence in first choice (1-7)"),
    ("tlx_mental", "NASA-TLX mental demand"),
    ("tlx_physical", "NASA-TLX physical demand"),
    ("tlx_temporal", "NASA-TLX time pressure"),
    ("tlx_performance", "NASA-TLX performance"),
    ("tlx_effort", "NASA-TLX effort"),
    ("tlx_frustration", "NASA-TLX frustration"),
    ("sam_valence", "Mood: unpleasant (1) to pleasant (9)"),
    ("sam_arousal", "Mood: calm (1) to excited (9)"),
    ("help_helpful", "The AI help was useful (1-7)"),
    ("help_timing", "The AI help came at the right time (1-7)"),
    ("help_intrusive", "The AI help was annoying (1-7)"),
    ("trust_mean", "Mean of the 4 trust items (1-7)"),
    ("sus_score", "System Usability Scale for this condition (0-100)"),
    ("preference_rank", "Participant's ranking of this condition (1 = best)"),
]
COLUMN_NAMES = [c for c, _ in COLUMNS]
KEY_COLUMNS = ("site", "participant", "task_key")
EXTRA_DISPLAY = "source"          # added in front when showing/downloading: "this laptop" or the uploaded file name

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_UPLOAD_ROWS = 50000


def site_name():
    name = (db.get_setting("site_name") or "").strip()
    return name or socket.gethostname()[:64]


def _yes(v):
    return None if v is None else bool(v)


def _num(v):
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else round(f, 3)


def local_rows(study, include_sim=False):
    """Rows built from this laptop's own database."""
    site = site_name()
    out = []
    with db.engine.connect() as conn:
        q = select(db.participants).where(db.participants.c.study == study).order_by(db.participants.c.id)
        if not include_sim:
            q = q.where(db.participants.c.simulated.is_(False))
        people = [dict(r._mapping) for r in conn.execute(q)]
        for p in people:
            tasks = [dict(r._mapping) for r in conn.execute(
                select(db.tasks).where(db.tasks.c.participant_id == p["id"])
                .where(db.tasks.c.kind.in_(("main", "pilot_ai"))).order_by(db.tasks.c.position))]
            resp = {}
            sus_by_cond, ranks = {}, {}
            for r in conn.execute(select(db.responses.c.kind, db.responses.c.task_key, db.responses.c.data)
                                  .where(db.responses.c.participant_id == p["id"])):
                d = db.loads(r.data, {}) or {}
                resp[(r.kind, r.task_key)] = d
                if r.kind == "sus" and d.get("condition"):
                    sus_by_cond[d["condition"]] = sus_score(d)
                if r.kind == "ranking":
                    ranks = d.get("ranks") or {}
            for t in tasks:
                pops = [dict(r._mapping) for r in conn.execute(select(db.popups).where(db.popups.c.task_id == t["id"]))]
                n_ai = len(conn.execute(select(db.ai_requests.c.id).where(db.ai_requests.c.task_id == t["id"])).all())
                lab = conn.execute(select(db.labels.c.intervals).where(db.labels.c.task_id == t["id"])).first()
                post = resp.get(("post_task", t["task_key"]), {})
                conf = resp.get(("confidence", t["task_key"]), {}).get("confidence", post.get("confidence"))
                trust = [float(post[k]) for k in ("trust1", "trust2", "trust3", "trust4") if post.get(k) not in (None, "")]
                cond = t["condition"]
                row = {
                    "site": site, "participant": p["code"], "study": study, "status": p["status"],
                    "excluded": bool(p["excluded"]), "simulated": bool(p["simulated"]),
                    "date": p["created_at"].date().isoformat() if p["created_at"] else None,
                    "round": t["position"], "task_key": t["task_key"], "condition": cond,
                    "condition_name": CONDITIONS.get(cond, {}).get("name", cond), "phone_set": t["set_id"],
                    "decision_time_s": round(t["decision_ms"] / 1000, 2) if t["decision_ms"] is not None else None,
                    "chosen_phone": t["chosen"], "correct": _yes(t["correct"]), "rank": t["rank"],
                    "switched": _yes(t["switched"]), "final_choice": t["final_choice"],
                    "final_correct": _yes(t["final_correct"]), "final_rank": t["final_rank"],
                    "popups_shown": len(pops),
                    "unsure_yes": sum(1 for x in pops if x["unsure_answer"] == "yes"),
                    "unsure_no": sum(1 for x in pops if x["unsure_answer"] == "no"),
                    "help_accepted": sum(1 for x in pops if x["choice"] in ("compare", "explain", "general")),
                    "help_dismissed": sum(1 for x in pops if x["choice"] == "dismiss"),
                    "ai_requests": n_ai,
                    "unsure_moments_marked": len(db.loads(lab[0], []) or []) if lab else None,
                    "confidence": _num(conf),
                    "sam_valence": _num(post.get("valence")), "sam_arousal": _num(post.get("arousal")),
                    "help_helpful": _num(post.get("helpful")), "help_timing": _num(post.get("timing")),
                    "help_intrusive": _num(post.get("intrusive")),
                    "trust_mean": round(st.mean(trust), 2) if trust else None,
                    "sus_score": sus_by_cond.get(cond), "preference_rank": _num(ranks.get(cond)),
                }
                for k in TLX_KEYS:
                    row[f"tlx_{k}"] = _num(post.get(k))
                row[EXTRA_DISPLAY] = "this laptop"
                out.append(row)
    return out


def imported(study):
    with db.engine.connect() as conn:
        rows = conn.execute(select(db.imported_rows.c.data, db.import_batches.c.filename)
                            .join(db.import_batches, db.import_batches.c.id == db.imported_rows.c.batch_id)
                            .where(db.imported_rows.c.study == study).order_by(db.imported_rows.c.id)).all()
    out = []
    for data, fname in rows:
        d = json.loads(data)
        d[EXTRA_DISPLAY] = f"uploaded: {fname}"
        out.append(d)
    return out


def all_rows(study, include_imported=True, include_sim=False):
    rows = local_rows(study, include_sim)
    if include_imported:
        rows += [r for r in imported(study) if include_sim or not r.get("simulated")]
    return rows


def display_columns():
    return [EXTRA_DISPLAY] + COLUMN_NAMES


# ---------------------------------------------------------------- download
def to_xlsx(include_imported=True, include_sim=False) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    cols = display_columns()
    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="3355CC")
    for study in STUDIES:
        ws = wb.create_sheet(SHEET_NAMES[study])
        ws.append(cols)
        for c in ws[1]:
            c.font, c.fill = head_font, head_fill
        for r in all_rows(study, include_imported, include_sim):
            ws.append([r.get(c) for c in cols])
        ws.freeze_panes = "C2"
        ws.auto_filter.ref = ws.dimensions
        for i, c in enumerate(cols, start=1):
            ws.column_dimensions[get_column_letter(i)].width = max(10, min(28, len(c) + 4))
    about = wb.create_sheet("About")
    about.append(["Beyond Clicks study results", f"downloaded {datetime.now():%Y-%m-%d %H:%M} from laptop '{site_name()}'"])
    about.append(["One row per participant and shopping round. Sheets 'Pilot' and 'Main' have the same columns."])
    about.append(["To combine laptops: upload this file in another laptop's dashboard (Data & Excel tab)."])
    about.append([])
    about.append(["Column", "Meaning"])
    about.append([EXTRA_DISPLAY, "Where the row came from: this laptop, or the file it was uploaded from"])
    for c, meaning in COLUMNS:
        about.append([c, meaning])
    about.column_dimensions["A"].width, about.column_dimensions["B"].width = 24, 80
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_csv(study, include_imported=True, include_sim=False) -> bytes:
    cols = display_columns()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in all_rows(study, include_imported, include_sim):
        w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])
    return ("﻿" + buf.getvalue()).encode("utf-8")     # BOM so Excel opens it with the right encoding


# ---------------------------------------------------------------- upload
def _clean_value(v):
    if isinstance(v, (datetime, date)):
        return v.date().isoformat() if isinstance(v, datetime) else v.isoformat()
    if isinstance(v, str):
        s = v.strip()
        if s.upper() in ("TRUE", "FALSE"):
            return s.upper() == "TRUE"
        if s == "":
            return None
        try:
            f = float(s)
            return int(f) if f.is_integer() and "." not in s else f
        except ValueError:
            return s
    return v


def _tables_from_upload(filename, content):
    """Returns {study: (header, rows)} from an .xlsx (sheets Pilot/Main) or a .csv (study column)."""
    name = filename.lower()
    found = {}
    if name.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001 - any parse failure is reported to the researcher
            raise ValueError(f"Could not read the Excel file: {e}") from e
        for ws in wb.worksheets:
            study = ws.title.strip().lower()
            if study not in STUDIES:
                continue
            it = ws.iter_rows(values_only=True)
            header = [str(h).strip() if h is not None else "" for h in (next(it, None) or [])]
            found[study] = (header, [list(r) for r in it])
        if not found:
            raise ValueError("No sheet named 'Pilot' or 'Main' was found. Use the file downloaded from the dashboard.")
    elif name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        rd = list(csv.reader(io.StringIO(text)))
        if not rd:
            raise ValueError("The CSV file is empty.")
        header = [h.strip() for h in rd[0]]
        if "study" not in header:
            raise ValueError("The CSV needs a 'study' column (pilot or main).")
        si = header.index("study")
        for r in rd[1:]:
            s = (r[si] if si < len(r) else "").strip().lower()
            if s in STUDIES:
                found.setdefault(s, (header, []))[1].append(r)
    else:
        raise ValueError("Upload an .xlsx or .csv file.")
    return found


def import_file(filename, content):
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("File is larger than 15 MB.")
    tables = _tables_from_upload(filename, content)
    own_site = site_name()
    report = {"filename": filename, "added": 0, "skipped_duplicates": 0, "skipped_own_laptop": 0,
              "skipped_empty": 0, "missing_columns": [], "ignored_columns": [], "per_study": {}}
    pending = []
    for study, (header, rows) in tables.items():
        missing_keys = [k for k in KEY_COLUMNS if k not in header]
        if missing_keys:
            raise ValueError(f"Sheet '{SHEET_NAMES[study]}' is missing required column(s): {', '.join(missing_keys)}.")
        report["missing_columns"] = sorted(set(report["missing_columns"]) | {c for c in COLUMN_NAMES if c not in header})
        report["ignored_columns"] = sorted(set(report["ignored_columns"]) |
                                           {h for h in header if h and h not in COLUMN_NAMES and h != EXTRA_DISPLAY})
        idx = {h: i for i, h in enumerate(header) if h in COLUMN_NAMES}
        for r in rows:
            d = {c: _clean_value(r[i]) if i < len(r) else None for c, i in idx.items()}
            if not d.get("participant") or not d.get("task_key"):
                report["skipped_empty"] += 1
                continue
            d["site"] = str(d.get("site") or "unknown")
            d["participant"], d["task_key"] = str(d["participant"]), str(d["task_key"])
            d["study"] = study
            if d["site"] == own_site:          # this laptop's own rows: already shown from the live database
                report["skipped_own_laptop"] += 1
                continue
            pending.append((study, d))
    if len(pending) > MAX_UPLOAD_ROWS:
        raise ValueError(f"Too many rows ({len(pending)}); the limit is {MAX_UPLOAD_ROWS}.")
    with db.engine.begin() as conn:
        bid = conn.execute(db.import_batches.insert().values(filename=filename[:255], uploaded_at=db.now(),
                                                             rows_added=0, rows_skipped=0)).inserted_primary_key[0]
        seen = set()
        for study, d in pending:
            key = (study, d["site"], d["participant"], d["task_key"])
            dup = key in seen or conn.execute(select(db.imported_rows.c.id).where(
                db.imported_rows.c.study == study, db.imported_rows.c.site == d["site"],
                db.imported_rows.c.participant == d["participant"],
                db.imported_rows.c.task_key == d["task_key"])).first()
            if dup:
                report["skipped_duplicates"] += 1
                continue
            seen.add(key)
            conn.execute(db.imported_rows.insert().values(batch_id=bid, study=study, site=d["site"],
                                                          participant=d["participant"], task_key=d["task_key"],
                                                          data=json.dumps(d, default=str)))
            report["added"] += 1
            report["per_study"][study] = report["per_study"].get(study, 0) + 1
        skipped = report["skipped_duplicates"] + report["skipped_own_laptop"] + report["skipped_empty"]
        conn.execute(db.import_batches.update().where(db.import_batches.c.id == bid)
                     .values(rows_added=report["added"], rows_skipped=skipped))
        if report["added"] == 0:
            conn.execute(db.import_batches.delete().where(db.import_batches.c.id == bid))
        db.log_audit("import", {k: report[k] for k in ("filename", "added", "skipped_duplicates", "skipped_own_laptop")},
                     conn=conn)
    return report


def batches():
    with db.engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(db.import_batches).order_by(db.import_batches.c.id.desc()))]


def delete_batch(bid):
    with db.engine.begin() as conn:
        conn.execute(db.imported_rows.delete().where(db.imported_rows.c.batch_id == bid))
        n = conn.execute(db.import_batches.delete().where(db.import_batches.c.id == bid)).rowcount
        db.log_audit("import_deleted", {"batch": bid}, conn=conn)
    return n
