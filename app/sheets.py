"""Overview: one row per participant x shopping round (pilot and main), with every result and the round's mouse
summary. Shown on the dashboard ("View data") and downloaded as the Overview CSV.

Built fresh from the study database every time, so it always includes every participant so far. It is computed from
the data, so it is never uploaded: to move the data between laptops use the Pilot and Main CSVs (app/datacsv.py).
"""
import csv
import io
import socket
import statistics as st

from sqlalchemy import select

from . import analysis, db, mouse, phones
from .analysis import TLX_KEYS, sus_score
from .defaults import CONDITIONS, DETECTOR_DEFAULTS

STUDIES = ("pilot", "main")

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


def loaded_info(study):
    """What was uploaded for this study (file, source laptop, times), or None if the data was recorded here."""
    loaded = db.get_setting("loaded_data") or {}
    return loaded.get(study) if isinstance(loaded.get(study), dict) else None


def data_site(study):
    """Laptop that recorded the data shown: the source laptop if that study's CSV was uploaded, else this one."""
    return (loaded_info(study) or {}).get("from_site") or site_name()


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
    site = data_site(study)
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


def overview_csv(include_sim=False) -> bytes:
    """Pilot rows, then main rows, each sorted by participant and round."""
    cols = display_columns()
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for study in STUDIES:
        rows = sorted(local_rows(study, include_sim), key=lambda r: (r["participant"], r["round"] or 0))
        w.writerows([r.get(c) for c in cols] for r in rows)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")       # BOM: Excel opens it as UTF-8 (the rupee sign etc.)
