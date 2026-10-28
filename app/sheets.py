"""Results sheet: one row per participant x shopping round, as an Excel workbook (Pilot + Main sheets).

Built fresh from the study database every time, so it always includes every participant so far. To move the full
data between laptops use the study-data CSV (app/datacsv.py), not this sheet.
"""
import io
import socket
import statistics as st
from datetime import datetime

from openpyxl import Workbook
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


def site_name():
    name = (db.get_setting("site_name") or "").strip()
    return name or socket.gethostname()[:64]


def data_site():
    """Laptop that recorded the data shown: the source laptop if a study-data CSV was loaded, else this one."""
    loaded = db.get_setting("loaded_data") or {}
    return loaded.get("from_site") or site_name()


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
    site = data_site()
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
                out.append(row)
    return out


def display_columns():
    return list(COLUMN_NAMES)


def to_xlsx(include_sim=False) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    cols = display_columns()
    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="3355CC")
    for study in STUDIES:
        ws = wb.create_sheet(SHEET_NAMES[study])
        ws.append(cols)
        for c in ws[1]:
            c.font, c.fill = head_font, head_fill
        for r in local_rows(study, include_sim):
            ws.append([r.get(c) for c in cols])
        ws.freeze_panes = "C2"
        ws.auto_filter.ref = ws.dimensions
        for i, c in enumerate(cols, start=1):
            ws.column_dimensions[get_column_letter(i)].width = max(10, min(28, len(c) + 4))
    about = wb.create_sheet("About")
    about.append(["Beyond Clicks study results", f"downloaded {datetime.now():%Y-%m-%d %H:%M} from laptop '{site_name()}'"])
    about.append(["One row per participant and shopping round. Sheets 'Pilot' and 'Main' have the same columns."])
    about.append([])
    about.append(["Column", "Meaning"])
    for c, meaning in COLUMNS:
        about.append([c, meaning])
    about.column_dimensions["A"].width, about.column_dimensions["B"].width = 24, 80
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
