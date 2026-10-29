"""Study data as CSV files, one per study: the Pilot CSV and the Main CSV.

Each file holds everything recorded for that study's participants (rounds, answers, pop-ups, AI answers, replay
labels and every mouse event) plus that study's settings (the Pilot CSV carries the freeze and the pilot analysis).
Download them on the laptop that ran the experiment; upload them on another laptop and every dashboard page, the
pilot analysis, the freeze, the main-study results, the Overview CSV and analysis/make_figures.py use that data.
Uploading a Pilot CSV replaces only the pilot data, uploading a Main CSV only the main-study data.

Format (version 3), sorted by participant, then round, then time:
  table, participant, study, task_key, round      who and where (filled on every line)
  t_ms, type, x, y, scroll_y, zone, clicked       mouse events: one line per event (table = "mouse")
  key, part, parts, data                          other lines: one database row as JSON in `data` (dates as
                                                  {"$dt": iso}, binary as {"$b64": base64}); rows longer than 30,000
                                                  characters continue on the next lines (part 1..parts)
The first line after the header is the `_meta` line (format, study, laptop, row counts). A file whose counts do not
match is refused before anything changes. Database ids are renumbered on upload, so the two files never collide.
"""
import base64
import csv
import io
import json
import secrets
from datetime import date, datetime

from sqlalchemy import select

from . import db, live

FORMAT = "beyond-clicks-study-data"
VERSION = 3
STUDIES = ("pilot", "main")
CHUNK = 30000                       # Excel's cell limit is 32,767 characters
MAX_BYTES = 500 * 1024 * 1024
# settings that belong to each study's file; the rest (laptop name, consent text) stay with the laptop
STUDY_SETTINGS = {"pilot": ("detector", "frozen", "pilot_analysis_last", "assignment_pilot", "pilot_ai_check_next"),
                  "main": ("assignment_main",)}
HEAD = ["table", "participant", "study", "task_key", "round", "t_ms", "type", "x", "y", "scroll_y", "zone", "clicked",
        "key", "part", "parts", "data"]
TABLES = ("settings", "participants", "tasks", "popups", "ai_requests", "labels", "responses", "audit")
TABLE_OBJ = {"settings": db.settings_t, "participants": db.participants, "tasks": db.tasks, "popups": db.popups,
             "ai_requests": db.ai_requests, "labels": db.labels, "responses": db.responses, "audit": db.audit,
             "event_batches": db.event_batches}
DAMAGED = "Download it again and upload it exactly as it was downloaded (do not open and save it in Excel first)."


def _enc(v):
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"$b64": base64.b64encode(bytes(v)).decode("ascii")}
    if isinstance(v, (datetime, date)):
        return {"$dt": v.isoformat()}
    return v


def _dec(v):
    if isinstance(v, dict) and len(v) == 1:
        if "$b64" in v:
            return base64.b64decode(v["$b64"])
        if "$dt" in v:
            return datetime.fromisoformat(v["$dt"])
    return v


def _rows(conn, tbl, where=None, order=None):
    q = select(tbl)
    if where is not None:
        q = q.where(where)
    return [dict(r._mapping) for r in conn.execute(q.order_by(order if order is not None else tbl.c.id))]


# ---------------------------------------------------------------- download
def export_csv(site, study) -> bytes:
    if study not in STUDIES:
        raise ValueError("Unknown study")
    lines, counts = [], {t: 0 for t in TABLES + ("event_batches", "mouse_events")}

    def row(tname, r, who=("", "", "", "")):
        counts[tname] += 1
        key = str(r["key"] if tname == "settings" else r["id"])
        data = json.dumps({k: _enc(v) for k, v in r.items()}, separators=(",", ":"))
        parts = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)] or [""]
        for i, chunk in enumerate(parts, start=1):
            lines.append([tname, *who] + [""] * 7 + [key, i, len(parts), chunk])

    with db.engine.connect() as conn:
        for r in _rows(conn, db.settings_t, db.settings_t.c.key.in_(STUDY_SETTINGS[study]), db.settings_t.c.key):
            row("settings", r)
        people = _rows(conn, db.participants, db.participants.c.study == study, db.participants.c.code)
        for p in people:
            p.pop("token", None)                            # session secrets are never exported
            code = p["code"]
            row("participants", p, (code, study, "", ""))
            resp = _rows(conn, db.responses, db.responses.c.participant_id == p["id"])
            for r in resp:
                if not r["task_key"]:
                    row("responses", r, (code, study, "", ""))
            for t in _rows(conn, db.tasks, db.tasks.c.participant_id == p["id"]):
                who = (code, study, t["task_key"], t["position"] if t["position"] is not None else "")
                row("tasks", t, who)
                for tname in ("popups", "ai_requests", "labels"):
                    tbl = TABLE_OBJ[tname]
                    for r in _rows(conn, tbl, tbl.c.task_id == t["id"]):
                        row(tname, r, who)
                for r in resp:
                    if r["task_key"] == t["task_key"]:
                        row("responses", r, who)
                lines.extend(_mouse_lines(conn, t["id"], who, counts))
        if study == "pilot":                                # freeze / unfreeze history goes with the freeze
            for r in _rows(conn, db.audit):
                row("audit", r)
    meta = {"format": FORMAT, "version": VERSION, "study": study, "site": site,
            "exported_at": datetime.now().isoformat(timespec="seconds"), "counts": counts}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEAD)
    w.writerow(["_meta", "", study, "", ""] + [""] * 7 + ["meta", 1, 1, json.dumps(meta)])
    w.writerows(lines)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _mouse_lines(conn, task_id, who, counts):
    """One readable line per logged mouse event of one task, in time order. Batches sent while the mouse was
    still carry no events and are not written."""
    ev, keys = [], set()
    for b in conn.execute(select(db.event_batches.c.seq, db.event_batches.c.data)
                          .where(db.event_batches.c.task_id == task_id).order_by(db.event_batches.c.seq)):
        d = db.unpack(b.data, {}) or {}
        key = f"{task_id}/{b.seq}"
        before = len(ev)
        ev += [(e[0], 0, key, "move", e[1], e[2], "", e[3], "") for e in d.get("m", [])]
        ev += [(e[0], 1, key, "scroll", "", "", e[1], e[2], "") for e in d.get("s", [])]
        ev += [(e[0], 2, key, "click", e[1], e[2], "", e[3], e[4] if len(e) > 4 else "") for e in d.get("c", [])]
        if len(ev) > before:
            keys.add(key)
    ev.sort(key=lambda e: (e[0], e[1]))                    # stable: same-time events keep their order
    counts["event_batches"] += len(keys)
    counts["mouse_events"] += len(ev)
    return [["mouse", *who, tm, typ, x, y, sy, zone if zone is not None else "", clicked if clicked is not None else "",
             key, "", "", ""] for tm, _, key, typ, x, y, sy, zone, clicked in ev]


# ---------------------------------------------------------------- upload
def _num(v):
    f = float(v)
    return int(f) if f.is_integer() else f


def _parse(content, study):
    """Reads and checks a whole file. Raises ValueError with a message for the researcher."""
    if len(content) > MAX_BYTES:
        raise ValueError("The file is larger than 500 MB.")
    if isinstance(content, bytes) and content[:2] == b"PK":
        raise ValueError("This is an Excel file, not a study CSV. Upload the CSV from 'Download pilot CSV' or "
                         "'Download main CSV'.")
    try:
        text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    except UnicodeDecodeError:
        raise ValueError("This file is not a study CSV as downloaded from the dashboard (it was probably opened and "
                         "saved again in Excel, which changes it). " + DAMAGED) from None
    csv.field_size_limit(10 * 1024 * 1024)
    rd = csv.reader(io.StringIO(text))
    head = [h.strip() for h in (next(rd, None) or [])]
    if head[:2] == ["table", "key"]:
        raise ValueError("This CSV was made by an older version of the study website. Update the website on the "
                         "laptop that ran the study, then download the pilot and main CSVs again.")
    if head != HEAD:
        raise ValueError("This is not a study CSV. Use the file from 'Download pilot CSV' or 'Download main CSV'.")
    col = {h: i for i, h in enumerate(HEAD)}
    meta, pieces, mouse = None, {}, {}
    for n, line in enumerate(rd, start=2):
        if not line:
            continue
        line = line + [""] * (len(HEAD) - len(line))
        tname = line[0]
        try:
            if tname == "_meta":
                meta = json.loads(line[col["data"]])
            elif tname == "mouse":
                ev = line[col["t_ms"]:col["clicked"] + 1]
                mouse.setdefault(line[col["key"]], []).append(ev)
            else:
                p = pieces.setdefault((tname, line[col["key"]]), {"parts": int(line[col["parts"]]), "chunks": {}})
                p["chunks"][int(line[col["part"]])] = line[col["data"]]
        except (ValueError, json.JSONDecodeError):
            raise ValueError(f"Line {n} of the file is damaged. " + DAMAGED) from None
    if not meta or meta.get("format") != FORMAT:
        raise ValueError("This is not a study CSV. Use the file from 'Download pilot CSV' or 'Download main CSV'.")
    if meta.get("version", 0) > VERSION:
        raise ValueError("This file was made by a newer version of the study website. Update this copy first.")
    if meta.get("study") != study:
        other = meta.get("study")
        raise ValueError(f"This is the {other} CSV. Upload it with 'Upload {other} CSV'." if other in STUDIES
                         else "This file does not say which study it belongs to. " + DAMAGED)
    rows = {t: [] for t in TABLES}
    for (tname, key), p in pieces.items():
        if tname not in rows:
            continue
        if len(p["chunks"]) != p["parts"]:
            raise ValueError(f"The file is incomplete ({tname} row {key} is cut off). " + DAMAGED)
        try:
            data = json.loads("".join(p["chunks"][i] for i in range(1, p["parts"] + 1)))
        except (KeyError, json.JSONDecodeError):
            raise ValueError(f"The file is damaged ({tname} row {key}). " + DAMAGED) from None
        rows[tname].append({k: _dec(v) for k, v in data.items()})
    try:
        rows["event_batches"] = _batches_from_mouse(mouse)
    except (ValueError, IndexError):
        raise ValueError("The mouse lines in the file are damaged. " + DAMAGED) from None
    expected = meta.get("counts") or {}
    got = {t: len(v) for t, v in rows.items()}
    got["mouse_events"] = sum(len(v) for v in mouse.values())
    short = [f"{t} {got.get(t, 0)}/{n}" for t, n in expected.items() if got.get(t, 0) != n]
    if short or not expected:
        raise ValueError("The file is incomplete or was changed (" + (", ".join(short) or "no row counts") + "). "
                         + DAMAGED)
    return meta, rows


def _batches_from_mouse(mouse):
    """Readable mouse lines back into event_batches rows (one per task and batch number)."""
    out = []
    for key, lines in mouse.items():
        task_id, seq = (int(x) for x in key.split("/"))
        d = {"m": [], "s": [], "c": []}
        for t, typ, x, y, sy, zone, clicked in lines:
            if typ == "move":
                d["m"].append([_num(t), _num(x), _num(y), zone])
            elif typ == "scroll":
                d["s"].append([_num(t), _num(sy), zone])
            elif typ == "click":
                d["c"].append([_num(t), _num(x), _num(y), zone, clicked])
            else:
                raise ValueError(typ)
        out.append({"task_id": task_id, "seq": seq, "data": db.pack(d)})
    return out


def check(content, study):
    """Checks a file without changing anything (used before the automatic backup)."""
    return _parse(content, study)[0]


def load_csv(content, filename, study):
    """Replaces this laptop's data for one study (participants and everything recorded, the study's settings; the
    pilot file also the audit log) with the file's data. New database ids are given; links are kept."""
    meta, rows = _parse(content, study)
    cols = {t: {c.name for c in TABLE_OBJ[t].columns} for t in TABLE_OBJ}

    def insert(conn, tname, r, **links):
        r = {k: v for k, v in r.items() if k in cols[tname] and k != "id"}
        r.update(links)
        return conn.execute(TABLE_OBJ[tname].insert().values(**r)).inserted_primary_key[0]

    with db.engine.begin() as conn:
        pids = [r[0] for r in conn.execute(select(db.participants.c.id).where(db.participants.c.study == study))]
        tids = [r[0] for r in conn.execute(select(db.tasks.c.id).where(db.tasks.c.participant_id.in_(pids)))] if pids else []
        if tids:
            for tbl in (db.event_batches, db.popups, db.ai_requests, db.labels):
                conn.execute(tbl.delete().where(tbl.c.task_id.in_(tids)))
            conn.execute(db.tasks.delete().where(db.tasks.c.id.in_(tids)))
        if pids:
            conn.execute(db.responses.delete().where(db.responses.c.participant_id.in_(pids)))
            conn.execute(db.participants.delete().where(db.participants.c.id.in_(pids)))
        conn.execute(db.settings_t.delete().where(db.settings_t.c.key.in_(STUDY_SETTINGS[study])))
        if study == "pilot":
            conn.execute(db.audit.delete())

        for r in rows["settings"]:
            if r.get("key") in STUDY_SETTINGS[study]:
                conn.execute(db.settings_t.insert().values(**{k: v for k, v in r.items() if k in cols["settings"]}))
        pmap, tmap, popmap = {}, {}, {}
        for r in sorted(rows["participants"], key=lambda x: x["id"]):
            if r.get("study") == study:
                pmap[r["id"]] = insert(conn, "participants", r, token=secrets.token_urlsafe(24))
        for r in sorted(rows["tasks"], key=lambda x: x["id"]):
            if r["participant_id"] in pmap:
                tmap[r["id"]] = insert(conn, "tasks", r, participant_id=pmap[r["participant_id"]])
        for r in sorted(rows["popups"], key=lambda x: x["id"]):
            if r["task_id"] in tmap:
                popmap[r["id"]] = insert(conn, "popups", r, task_id=tmap[r["task_id"]])
        for r in sorted(rows["ai_requests"], key=lambda x: x["id"]):
            if r["task_id"] in tmap:
                insert(conn, "ai_requests", r, task_id=tmap[r["task_id"]], popup_id=popmap.get(r.get("popup_id")))
        for r in rows["labels"]:
            if r["task_id"] in tmap:
                insert(conn, "labels", r, task_id=tmap[r["task_id"]])
        for r in sorted(rows["responses"], key=lambda x: x["id"]):
            if r["participant_id"] in pmap:
                insert(conn, "responses", r, participant_id=pmap[r["participant_id"]])
        batches = [dict(b, task_id=tmap[b["task_id"]], created_at=db.now()) for b in rows["event_batches"]
                   if b["task_id"] in tmap]
        for i in range(0, len(batches), 500):
            conn.execute(db.event_batches.insert(), batches[i:i + 500])
        for r in sorted(rows["audit"], key=lambda x: x["id"]):
            insert(conn, "audit", r)

        counts = {"participants": len(pmap), "rounds_and_tasks": len(tmap), "mouse_events": meta["counts"]["mouse_events"],
                  "answers": len(rows["responses"])}
        info = {"filename": filename, "study": study, "from_site": meta.get("site"),
                "exported_at": meta.get("exported_at"), "loaded_at": datetime.now().isoformat(timespec="seconds"),
                "counts": counts}
        old = conn.execute(select(db.settings_t.c.value).where(db.settings_t.c.key == "loaded_data")).first()
        loaded = (db.loads(old[0]) if old else None) or {}
        loaded = {k: v for k, v in loaded.items() if k in STUDIES}
        loaded[study] = info
        db.set_setting("loaded_data", loaded, conn=conn)
        db.log_audit("data_loaded", info, conn=conn)
    live._tasks.clear()                                   # no stale live state from the previous data
    return info
