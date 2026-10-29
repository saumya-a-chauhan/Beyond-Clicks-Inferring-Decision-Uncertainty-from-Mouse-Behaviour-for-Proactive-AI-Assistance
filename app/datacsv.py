"""Study data as ONE CSV file: everything recorded on a laptop (participants, rounds, raw mouse movement, answers,
pop-ups, AI answers, replay labels, settings including the freeze, audit log).

Download it on the laptop that ran the experiment, load it on another laptop, and every dashboard page, the pilot
analysis, the freeze, the main-study results, the Excel download and analysis/make_figures.py run on that data.

Format: columns table, key, part, parts, data. `data` is one database row as JSON (dates as {"$dt": iso}, binary as
{"$b64": base64}). Long rows are split over several lines (part 1..parts) so no cell is longer than Excel allows.
The first line after the header is the `_meta` row that identifies the file.

The mouse movement is written in readable form (version 2): one line per logged event with table = "mouse" and the
columns participant, study, task_key, round, t_ms, type (move / scroll / click), x, y, scroll_y, zone, clicked.
`key` is "<task id>/<batch number>", so loading the file rebuilds exactly the same events. Files of version 1 (mouse
movement packed inside event_batches rows) still load.
"""
import base64
import csv
import io
import json
import secrets
from datetime import date, datetime

from sqlalchemy import delete, select

from . import db, live

FORMAT = "beyond-clicks-study-data"
VERSION = 2
CHUNK = 30000                       # Excel's cell limit is 32,767 characters
MAX_BYTES = 500 * 1024 * 1024
LOCAL_SETTINGS = {"site_name"}       # stay with the laptop, never copied

# parents before children, so ids and links stay valid
TABLES = [
    ("participants", db.participants),
    ("tasks", db.tasks),
    ("event_batches", db.event_batches),
    ("popups", db.popups),
    ("ai_requests", db.ai_requests),
    ("labels", db.labels),
    ("responses", db.responses),
    ("settings", db.settings_t),
    ("audit", db.audit),
]


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


def _key(tname, row):
    return str(row["key"] if tname == "settings" else row["id"])


MOUSE_COLS = ["participant", "study", "task_key", "round", "t_ms", "type", "x", "y", "scroll_y", "zone", "clicked"]
HEAD = ["table", "key", "part", "parts", "data"] + MOUSE_COLS


def _mouse_rows(conn):
    """One readable line per logged mouse event, per participant and task, in time order.
    Returns (lines, number of batches with events); batches sent while the mouse was still carry nothing."""
    people = {r.id: (r.code, r.study) for r in conn.execute(select(db.participants.c.id, db.participants.c.code,
                                                                   db.participants.c.study))}
    tasks = {r.id: r for r in conn.execute(select(db.tasks.c.id, db.tasks.c.participant_id, db.tasks.c.task_key,
                                                  db.tasks.c.position))}
    by_task = {}
    for b in conn.execute(select(db.event_batches.c.task_id, db.event_batches.c.seq, db.event_batches.c.data)
                          .order_by(db.event_batches.c.task_id, db.event_batches.c.seq)):
        d = db.unpack(b.data, {}) or {}
        key = f"{b.task_id}/{b.seq}"
        ev = by_task.setdefault(b.task_id, [])
        ev += [(e[0], 0, key, "move", e[1], e[2], "", e[3], "") for e in d.get("m", [])]
        ev += [(e[0], 1, key, "scroll", "", "", e[1], e[2], "") for e in d.get("s", [])]
        ev += [(e[0], 2, key, "click", e[1], e[2], "", e[3], e[4] if len(e) > 4 else "") for e in d.get("c", [])]
    lines, n_batches = [], 0
    for task_id in sorted(by_task):
        t = tasks.get(task_id)
        code, study = people.get(t.participant_id, ("", "")) if t else ("", "")
        ev = sorted(by_task[task_id], key=lambda e: (e[0], e[1]))       # stable: same-time events keep their order
        n_batches += len({e[2] for e in ev})
        for tm, _, key, typ, x, y, sy, zone, clicked in ev:
            lines.append(["mouse", key, "", "", "", code, study, t.task_key if t else "", t.position if t else "",
                          tm, typ, x, y, sy, zone if zone is not None else "", clicked if clicked is not None else ""])
    return lines, n_batches


def export_csv(site) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEAD)
    counts = {}
    rows_out = []
    with db.engine.connect() as conn:
        mouse, counts["event_batches"] = _mouse_rows(conn)
        counts["mouse_events"] = len(mouse)
        for tname, tbl in TABLES:
            if tname == "event_batches":                    # written below as readable mouse rows
                continue
            rows = [dict(r._mapping) for r in conn.execute(select(tbl))]
            if tname == "participants":
                for r in rows:
                    r.pop("token", None)                    # session secrets are never exported
            if tname == "settings":
                rows = [r for r in rows if r["key"] not in LOCAL_SETTINGS]
            counts[tname] = len(rows)
            for r in rows:
                rows_out.append((tname, _key(tname, r), json.dumps({k: _enc(v) for k, v in r.items()},
                                                                   separators=(",", ":"))))
    meta = {"format": FORMAT, "version": VERSION, "exported_at": datetime.now().isoformat(timespec="seconds"),
            "site": site, "counts": counts}
    w.writerow(["_meta", "meta", 1, 1, json.dumps(meta)])
    for tname, key, data in rows_out:
        parts = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)] or [""]
        for i, chunk in enumerate(parts, start=1):
            w.writerow([tname, key, i, len(parts), chunk])
    w.writerows(mouse)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _parse(content):
    if len(content) > MAX_BYTES:
        raise ValueError("The file is larger than 500 MB.")
    csv.field_size_limit(10 * 1024 * 1024)
    text = content.decode("utf-8-sig", errors="strict") if isinstance(content, bytes) else content
    rd = csv.reader(io.StringIO(text))
    head = next(rd, None)
    if not head or [h.strip() for h in head[:5]] != ["table", "key", "part", "parts", "data"]:
        raise ValueError("This is not a study-data CSV. Use the file from 'Download CSV' on the Data & Excel tab.")
    meta, pieces, mouse = None, {}, {}
    for line in rd:
        if len(line) < 5:
            continue
        tname, key, part, parts, data = line[:5]
        if tname == "mouse":
            mouse.setdefault(key, []).append(line[5:16])
            continue
        if tname == "_meta":
            meta = json.loads(data)
            continue
        pieces.setdefault((tname, key), {"parts": int(parts), "chunks": {}})["chunks"][int(part)] = data
    if not meta or meta.get("format") != FORMAT:
        raise ValueError("This is not a study-data CSV. Use the file from 'Download CSV' on the Data & Excel tab.")
    if meta.get("version", 0) > VERSION:
        raise ValueError("This file was made by a newer version of the study website. Update this copy first.")
    known = {t for t, _ in TABLES}
    rows = {t: [] for t in known}
    for (tname, key), p in pieces.items():
        if tname not in known:
            continue
        if len(p["chunks"]) != p["parts"]:
            raise ValueError(f"The file is incomplete ({tname} row {key} is cut off). Download it again.")
        data = "".join(p["chunks"][i] for i in range(1, p["parts"] + 1))
        try:
            rows[tname].append({k: _dec(v) for k, v in json.loads(data).items()})
        except json.JSONDecodeError as e:
            raise ValueError(f"The file is damaged ({tname} row {key}). Was it edited and saved in Excel? "
                             "Download it again and upload it without opening it.") from e
    if mouse:
        try:
            rows["event_batches"] = _batches_from_mouse(mouse)
        except (ValueError, IndexError) as e:
            raise ValueError("The mouse rows in the file are damaged. Was it edited and saved in Excel? "
                             "Download it again and upload it without opening it.") from e
    expected = dict(meta.get("counts") or {})
    n_mouse = sum(len(v) for v in mouse.values())
    if "mouse_events" in expected and expected.pop("mouse_events") != n_mouse:
        raise ValueError(f"The file is incomplete or was changed (mouse rows {n_mouse}/{meta['counts']['mouse_events']}). "
                         "Download it again and upload it without opening it.")
    short = [f"{t} {len(rows[t])}/{n}" for t, n in expected.items() if t in rows and len(rows[t]) != n]
    if short or not expected:
        raise ValueError("The file is incomplete or was changed (" + (", ".join(short) or "no row counts") +
                         "). Download it again and upload it without opening it.")
    return meta, rows


def _num(v):
    f = float(v)
    return int(f) if f.is_integer() else f


def _batches_from_mouse(mouse):
    """Readable mouse rows back into event_batches rows (one per task and batch number)."""
    out = []
    for key, lines in mouse.items():
        task_id, seq = (int(x) for x in key.split("/"))
        d = {"m": [], "s": [], "c": []}
        for ln in lines:
            ln = ln + [""] * (11 - len(ln))
            t, typ, x, y, sy, zone, clicked = ln[4:11]
            if typ == "move":
                d["m"].append([_num(t), _num(x), _num(y), zone])
            elif typ == "scroll":
                d["s"].append([_num(t), _num(sy), zone])
            elif typ == "click":
                d["c"].append([_num(t), _num(x), _num(y), zone, clicked])
            else:
                raise ValueError(typ)
        out.append({"task_id": task_id, "seq": seq, "data": db.pack(d), "created_at": db.now()})
    return out


def load_csv(content, filename):
    meta, rows = _parse(content)
    cols = {t: {c.name for c in tbl.columns} for t, tbl in TABLES}
    with db.engine.begin() as conn:
        for tname, tbl in reversed(TABLES):
            if tname == "settings":
                conn.execute(delete(tbl).where(tbl.c.key.not_in(LOCAL_SETTINGS)))
            else:
                conn.execute(delete(tbl))
        for tname, tbl in TABLES:
            batch = []
            for r in sorted(rows[tname], key=lambda x: (x.get("id") is None, x.get("id") or 0)):
                r = {k: v for k, v in r.items() if k in cols[tname]}
                if tname == "participants":
                    r["token"] = secrets.token_urlsafe(24)   # fresh secrets for this laptop
                if tname == "settings" and r.get("key") in LOCAL_SETTINGS:
                    continue
                batch.append(r)
                if len(batch) >= 500:
                    conn.execute(tbl.insert(), batch)
                    batch = []
            if batch:
                conn.execute(tbl.insert(), batch)
        info = {"filename": filename, "from_site": meta.get("site"), "exported_at": meta.get("exported_at"),
                "loaded_at": datetime.now().isoformat(timespec="seconds"),
                "counts": {t: len(v) for t, v in rows.items()}}
        db.set_setting("loaded_data", info, conn=conn)
        db.log_audit("data_loaded", info, conn=conn)
    live._tasks.clear()                                   # no stale live state from the previous data
    return info
