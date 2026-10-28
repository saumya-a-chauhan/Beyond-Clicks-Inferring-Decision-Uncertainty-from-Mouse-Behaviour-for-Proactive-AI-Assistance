"""Study data as ONE CSV file: everything recorded on a laptop (participants, rounds, raw mouse movement, answers,
pop-ups, AI answers, replay labels, settings including the freeze, audit log).

Download it on the laptop that ran the experiment, load it on another laptop, and every dashboard page, the pilot
analysis, the freeze, the main-study results, the Excel download and analysis/make_figures.py run on that data.

Format: columns table, key, part, parts, data. `data` is one database row as JSON (dates as {"$dt": iso}, binary as
{"$b64": base64}). Long rows are split over several lines (part 1..parts) so no cell is longer than Excel allows.
The first line after the header is the `_meta` row that identifies the file.
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
VERSION = 1
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


def export_csv(site) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["table", "key", "part", "parts", "data"])
    counts = {}
    rows_out = []
    with db.engine.connect() as conn:
        for tname, tbl in TABLES:
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
    meta, pieces = None, {}
    for line in rd:
        if len(line) < 5:
            continue
        tname, key, part, parts, data = line[:5]
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
    expected = meta.get("counts") or {}
    short = [f"{t} {len(rows[t])}/{n}" for t, n in expected.items() if t in rows and len(rows[t]) != n]
    if short or not expected:
        raise ValueError("The file is incomplete or was changed (" + (", ".join(short) or "no row counts") +
                         "). Download it again and upload it without opening it.")
    return meta, rows


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
