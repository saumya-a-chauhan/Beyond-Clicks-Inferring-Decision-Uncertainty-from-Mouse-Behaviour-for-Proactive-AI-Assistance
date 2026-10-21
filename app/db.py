"""Database tables (SQLite locally, Postgres in the cloud) and small helpers."""
import gzip
import json
from datetime import datetime, timezone

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer, LargeBinary,
                        MetaData, String, Table, Text, UniqueConstraint, create_engine, event,
                        select)

from . import config

engine = create_engine(
    config.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    **({"connect_args": {"check_same_thread": False}} if config.DATABASE_URL.startswith("sqlite") else {}),
)

if config.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

md = MetaData()

participants = Table(
    "participants", md,
    Column("id", Integer, primary_key=True),
    Column("code", String(16), unique=True, nullable=False),        # P01 (pilot) / M01 (main)
    Column("token", String(64), unique=True, nullable=False),        # secret, kept in the browser
    Column("study", String(8), nullable=False),                      # pilot | main
    Column("slot", Integer),                                         # assignment slot number
    Column("condition_order", Text),                                 # JSON list e.g. ["C2","C3","C1","C4"]
    Column("set_order", Text),                                       # JSON list e.g. ["S3","S4","S1","S2"]
    Column("pilot_ai_check", Boolean, default=False),
    Column("plan", Text),                                            # JSON list of steps
    Column("step_index", Integer, default=0),
    Column("status", String(16), default="started"),                 # started | completed | withdrawn
    Column("device", Text),                                          # JSON device info
    Column("baseline", Text),                                        # JSON per-person typical values / spreads
    Column("settings_snapshot", Text),                               # JSON detector settings used
    Column("excluded", Boolean, default=False),
    Column("simulated", Boolean, default=False),                     # fake data from scripts/simulate.py
    Column("notes", Text),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)

tasks = Table(
    "tasks", md,
    Column("id", Integer, primary_key=True),
    Column("participant_id", Integer, ForeignKey("participants.id", ondelete="CASCADE"), index=True),
    Column("task_key", String(16)),        # baseline1, baseline2, practice, t1..t4, ai
    Column("kind", String(16)),            # baseline | practice | main | pilot_ai
    Column("position", Integer),           # 1..4 for main tasks
    Column("condition", String(4)),        # C1..C4 (pilot main tasks = C1)
    Column("set_id", String(4)),
    Column("card_order", Text),            # JSON list of phone ids, left to right
    Column("viewport", Text),              # JSON {w,h,dpr}
    Column("started_at", DateTime(timezone=True)),
    Column("ended_at", DateTime(timezone=True)),
    Column("decision_ms", Integer),
    Column("chosen", String(8)),
    Column("correct", Boolean),
    Column("rank", Integer),
    Column("switched", Boolean),
    Column("final_choice", String(8)),
    Column("final_correct", Boolean),
    Column("final_rank", Integer),
    Column("ticks", LargeBinary),          # gzip JSON of detector ticks
    UniqueConstraint("participant_id", "task_key", name="uq_task"),
)

event_batches = Table(
    "event_batches", md,
    Column("id", Integer, primary_key=True),
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), index=True),
    Column("seq", Integer),
    Column("data", LargeBinary),           # gzip JSON {"m":[[t,x,y,zone]],"s":[[t,scrollY,zone]],"c":[[t,x,y,zone,label]]}
    Column("created_at", DateTime(timezone=True)),
    UniqueConstraint("task_id", "seq", name="uq_batch"),
)

popups = Table(
    "popups", md,
    Column("id", Integer, primary_key=True),
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), index=True),
    Column("t_ms", Integer),
    Column("source", String(12)),          # detector | random
    Column("predicted_type", String(12)),  # compare | explain | general
    Column("pair", Text),                  # JSON [phoneId, phoneId]
    Column("spec", String(16)),
    Column("score", Float),
    Column("zs", Text),                    # JSON z per sign
    Column("unsure_answer", String(4)),    # yes | no
    Column("unsure_ms", Integer),
    Column("choice", String(12)),          # compare | explain | dismiss
    Column("choice_ms", Integer),
    Column("closed_ms", Integer),
)

ai_requests = Table(
    "ai_requests", md,
    Column("id", Integer, primary_key=True),
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), index=True),
    Column("popup_id", Integer),
    Column("t_ms", Integer),
    Column("origin", String(8)),           # popup | ask
    Column("mode", String(12)),            # compare | explain | general | ask
    Column("args", Text),
    Column("provider", String(16)),        # gemini | groq | fallback | cache:<p>
    Column("model", String(64)),
    Column("response", Text),
    Column("latency_ms", Integer),
    Column("error", Text),
)

llm_cache = Table(
    "llm_cache", md,
    Column("key", String(255), primary_key=True),
    Column("response", Text),
    Column("provider", String(16)),
    Column("model", String(64)),
    Column("created_at", DateTime(timezone=True)),
)

labels = Table(
    "labels", md,
    Column("id", Integer, primary_key=True),
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), unique=True),
    Column("intervals", Text),             # JSON [[start_ms, end_ms], ...]
    Column("replay_speed", Float, default=1.0),
    Column("created_at", DateTime(timezone=True)),
)

responses = Table(
    "responses", md,
    Column("id", Integer, primary_key=True),
    Column("participant_id", Integer, ForeignKey("participants.id", ondelete="CASCADE"), index=True),
    Column("step_key", String(32)),
    Column("kind", String(24)),
    Column("task_key", String(16)),
    Column("data", Text),
    Column("created_at", DateTime(timezone=True)),
)

settings_t = Table(
    "settings", md,
    Column("key", String(64), primary_key=True),
    Column("value", Text),
    Column("updated_at", DateTime(timezone=True)),
)

audit = Table(
    "audit", md,
    Column("id", Integer, primary_key=True),
    Column("ts", DateTime(timezone=True)),
    Column("action", String(32)),
    Column("detail", Text),
)


def now():
    return datetime.now(timezone.utc)


def init_db():
    md.create_all(engine)


def dumps(o):
    return json.dumps(o, separators=(",", ":"))


def loads(s, default=None):
    if s is None or s == "":
        return default
    return json.loads(s)


def pack(o) -> bytes:
    return gzip.compress(dumps(o).encode("utf-8"))


def unpack(b, default=None):
    if not b:
        return default
    return json.loads(gzip.decompress(b).decode("utf-8"))


def get_setting(key, default=None):
    with engine.connect() as c:
        row = c.execute(select(settings_t.c.value).where(settings_t.c.key == key)).first()
    return loads(row[0]) if row else default


def set_setting(key, value, conn=None):
    def _do(c):
        exists = c.execute(select(settings_t.c.key).where(settings_t.c.key == key)).first()
        if exists:
            c.execute(settings_t.update().where(settings_t.c.key == key).values(value=dumps(value), updated_at=now()))
        else:
            c.execute(settings_t.insert().values(key=key, value=dumps(value), updated_at=now()))
    if conn is not None:
        _do(conn)
    else:
        with engine.begin() as c:
            _do(c)


def log_audit(action, detail, conn=None):
    stmt = audit.insert().values(ts=now(), action=action, detail=dumps(detail))
    if conn is not None:
        conn.execute(stmt)
    else:
        with engine.begin() as c:
            c.execute(stmt)


def task_events(conn, task_id):
    """All logged cursor events of a task, merged and sorted by time."""
    rows = conn.execute(select(event_batches.c.data).where(event_batches.c.task_id == task_id)
                        .order_by(event_batches.c.seq)).all()
    m, s, cl = [], [], []
    for (blob,) in rows:
        d = unpack(blob, {})
        m.extend(d.get("m", []))
        s.extend(d.get("s", []))
        cl.extend(d.get("c", []))
    m.sort(key=lambda e: e[0])
    s.sort(key=lambda e: e[0])
    cl.sort(key=lambda e: e[0])
    return {"m": m, "s": s, "c": cl}
