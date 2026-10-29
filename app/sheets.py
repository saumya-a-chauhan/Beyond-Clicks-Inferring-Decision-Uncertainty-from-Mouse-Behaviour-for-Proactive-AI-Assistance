"""Results sheet: one row per participant x shopping round, as an Excel workbook (Pilot + Main sheets).

Built fresh from the study database every time, so it always includes every participant so far. To move the full
data between laptops use the study-data CSV (app/datacsv.py), not this sheet.
"""
import io
import socket
import statistics as st
from datetime import datetime

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select

from . import analysis, db, mouse, phones
from .analysis import TLX_KEYS, sus_score
from .defaults import CONDITIONS, DETECTOR_DEFAULTS

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
    ("age", "Age in years (from the 'About you' step)"),
    ("gender", "woman, man, non-binary, prefer-not, or the participant's own words"),
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
] + mouse.SUMMARY_COLUMNS
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


def participant_cfg(p):
    """The detector settings this participant ran with (frozen snapshot, else the current settings)."""
    cfg = dict(DETECTOR_DEFAULTS)
    cfg.update(db.loads(p.get("settings_snapshot")) or analysis.detector_cfg())
    return cfg


def _people(conn, study, include_sim):
    q = select(db.participants).where(db.participants.c.study == study).order_by(db.participants.c.id)
    if not include_sim:
        q = q.where(db.participants.c.simulated.is_(False))
    return [dict(r._mapping) for r in conn.execute(q)]


def _names(set_id):
    s = phones.get_set(set_id) if set_id else None
    return {ph["id"]: ph["name"] for ph in s["phones"]} if s else {}


def local_rows(study, include_sim=False):
    """Rows built from this laptop's own database."""
    site = data_site()
    out = []
    with db.engine.connect() as conn:
        for p in _people(conn, study, include_sim):
            cfg = participant_cfg(p)
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
            demo = resp.get(("demographics", None), {})
            gender = demo.get("gender_self") or demo.get("gender") if demo.get("gender") == "self-describe" else demo.get("gender")
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
                    "age": _num(demo.get("age")), "gender": gender,
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
                ticks = db.unpack(t["ticks"], []) or []
                row.update(mouse.summary(db.task_events(conn, t["id"]), ticks, cfg, _names(t["set_id"])))
                out.append(row)
    return out


def display_columns():
    return list(COLUMN_NAMES)


MAX_ROWS = 1_000_000          # Excel allows 1,048,576 rows per sheet; longer data continues on a new sheet


class _Writer:
    """Write-only workbook (fast, low memory even with millions of mouse rows) with styled headers."""

    def __init__(self):
        self.wb = Workbook(write_only=True)
        self.head_font, self.head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="3355CC")

    def sheet(self, title, head, widths=None):
        ws = self.wb.create_sheet(title)
        for i, c in enumerate(head, start=1):
            ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(c, max(10, min(28, len(c) + 4)))
        ws.freeze_panes = "C2"
        cells = []
        for c in head:
            cell = WriteOnlyCell(ws, value=c)
            cell.font, cell.fill = self.head_font, self.head_fill
            cells.append(cell)
        ws.append(cells)
        return ws

    def long_sheet(self, title, head, rows):
        """Rows split over 'title', 'title 2', ... so no sheet passes Excel's row limit. Returns the row count."""
        ws, n, part = self.sheet(title, head), 0, 1
        for r in rows:
            if n and n % MAX_ROWS == 0:
                part += 1
                ws = self.sheet(f"{title} {part}", head)
            ws.append(r)
            n += 1
        return n


def _tasks(conn, p, kinds=None):
    q = select(db.tasks).where(db.tasks.c.participant_id == p["id"])
    if kinds:
        q = q.where(db.tasks.c.kind.in_(kinds))
    return conn.execute(q.order_by(db.tasks.c.id)).all()


def _mouse_sheets(w, include_sim):
    """Raw rows behind the mouse numbers: detector checks every 0.5 s, every logged event, replay marks."""
    def each_task(kinds=None):
        with db.engine.connect() as conn:
            for study in STUDIES:
                for p in _people(conn, study, include_sim):
                    for t in _tasks(conn, p, kinds):
                        yield conn, study, p, t

    def ticks():
        for conn, study, p, t in each_task(("main", "pilot_ai")):
            base = [p["code"], study, t.position, t.task_key, t.condition, t.set_id]
            yield from mouse.tick_rows(base, db.unpack(t.ticks, []) or [], participant_cfg(p))

    def events():
        for conn, study, p, t in each_task():
            yield from mouse.event_rows([p["code"], study, t.task_key, t.kind, t.position], db.task_events(conn, t.id))

    def marks():
        for conn, study, p, t in each_task(("main",)):
            lab = conn.execute(select(db.labels.c.intervals).where(db.labels.c.task_id == t.id)).first()
            for a, b in (db.loads(lab[0], []) or []) if lab else []:
                yield [p["code"], study, t.position, t.task_key, t.set_id,
                       round(a / 1000, 2), round(b / 1000, 2), round((b - a) / 1000, 2)]

    return {
        "Mouse signs": w.long_sheet("Mouse signs", mouse.TICK_HEAD, ticks()),
        "Mouse raw": w.long_sheet("Mouse raw", mouse.EVENT_HEAD, events()),
        "Unsure marks": w.long_sheet("Unsure marks", ["participant", "study", "round", "task_key", "phone_set",
                                                      "start_s", "end_s", "length_s"], marks()),
    }


MOUSE_SHEET_HELP = [
    ("Mouse signs", "One row per detector check (every 0.5 s) in each shopping round: the 5 raw signs over the last "
                    "3 s (B back-and-forth switches between phones, F longest rest on one spec in s, I longest rest in "
                    "empty space in s, W wandering ratio, S scroll flips), their z-scores against the person's warm-up "
                    "baseline, the hesitation score (mean of the 5 z-scores) and whether it was at or above the "
                    "threshold. all_seen = every phone card hovered for 1 s, needed before any pop-up."),
    ("Mouse raw", "Every logged event of every task (warm-ups and practice too). t_ms = milliseconds since the task "
                  "started; type = move (about 60 per second while the mouse moves), scroll or click; x, y = position "
                  "in the window in pixels; scroll_y = page scroll; zone = what was under the cursor (card:<phone>, "
                  "spec:<phone>:<spec>, read:card, empty, ui:...); clicked = the button clicked (details:<phone>, "
                  "buy:<phone>, ...). Continues on 'Mouse raw 2' etc. after 1,000,000 rows."),
    ("Unsure marks", "Pilot replay: each moment the participant held SPACE to mark 'I was unsure', in seconds from "
                     "the start of the round."),
]


def to_xlsx(include_sim=False, include_mouse=False) -> bytes:
    w = _Writer()
    cols = display_columns()
    for study in STUDIES:
        ws = w.sheet(SHEET_NAMES[study], cols, {"hover_by_phone": 48})
        rows = local_rows(study, include_sim)
        for r in rows:
            ws.append([r.get(c) for c in cols])
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(rows) + 1}"
    counts = _mouse_sheets(w, include_sim) if include_mouse else {}
    about = w.wb.create_sheet("About")
    about.column_dimensions["A"].width, about.column_dimensions["B"].width = 24, 100
    about.append(["Beyond Clicks study results", f"downloaded {datetime.now():%Y-%m-%d %H:%M} from laptop '{site_name()}'"])
    about.append(["One row per participant and shopping round. Sheets 'Pilot' and 'Main' have the same columns."])
    about.append(["Mouse data", ("included: " + ", ".join(f"{k} ({n:,} rows)" for k, n in counts.items())) if include_mouse
                  else "per-round summary only (tick 'Include all mouse-movement data' on the dashboard for every point)"])
    about.append([])
    about.append(["Column", "Meaning"])
    for c, meaning in COLUMNS:
        about.append([c, meaning])
    if include_mouse:
        about.append([])
        about.append(["Sheet", "What it holds"])
        for name, text in MOUSE_SHEET_HELP:
            about.append([name, text])
    buf = io.BytesIO()
    w.wb.save(buf)
    return buf.getvalue()
