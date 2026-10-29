"""Study-data CSV: everything survives download -> upload, and broken files are refused before anything changes."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_pytest.db")
if os.environ["DATABASE_URL"] == "sqlite:///./_pytest.db" and os.path.exists("_pytest.db"):
    os.remove("_pytest.db")                                # start from an empty test database every run

import pytest  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app import datacsv, db  # noqa: E402


def _counts():
    with db.engine.connect() as c:
        return {t: c.execute(select(func.count()).select_from(tb)).scalar() for t, tb in datacsv.TABLES
                if t not in ("audit", "settings")}


def _add_person(code):
    with db.engine.begin() as c:
        pid = c.execute(db.participants.insert().values(code=code, token=f"tok-{code}", study="pilot", status="started",
                                                        created_at=db.now(), updated_at=db.now())).inserted_primary_key[0]
        tid = c.execute(db.tasks.insert().values(participant_id=pid, task_key="t1", kind="main", position=1,
                                                 condition="C1", set_id="S1", started_at=db.now(),
                                                 ticks=db.pack([{"t": 500}]))).inserted_primary_key[0]
        c.execute(db.event_batches.insert().values(task_id=tid, seq=0, data=db.pack({"m": [[0, 1, 2, "c1"]] * 50}),
                                                   created_at=db.now()))


def test_round_trip_and_refusals(monkeypatch):
    db.init_db()
    _add_person("PX1")
    monkeypatch.setattr(datacsv, "CHUNK", 200)            # force long rows to be split over several lines
    data = datacsv.export_csv("laptop-A")
    before = _counts()
    assert b'"token"' not in data

    with pytest.raises(ValueError):
        datacsv.load_csv(b"a,b\n1,2\n", "wrong.csv")
    with pytest.raises(ValueError):
        datacsv.load_csv(data[: len(data) // 2], "cut.csv")
    assert _counts() == before                            # refused files change nothing

    _add_person("PX2")                                    # this laptop's own extra data ...
    db.set_setting("frozen", {"frozen": True, "threshold": 9.9})          # ... and its own freeze
    db.set_setting("site_name", "laptop-B")
    info = datacsv.load_csv(data, "good.csv")
    assert info["from_site"] == "laptop-A"
    assert _counts() == before                            # exactly the file's data afterwards (PX2 is gone)
    with db.engine.connect() as c:
        codes = set(c.execute(select(db.participants.c.code)).scalars())
    assert "PX2" not in codes and "PX1" in codes
    assert db.get_setting("frozen") is None               # the receiving laptop's freeze was overridden too
    assert db.get_setting("site_name") == "laptop-B"      # only the laptop's own name stays
    with db.engine.connect() as c:
        blob = c.execute(select(db.event_batches.c.data)).scalars().first()
        tok = c.execute(select(db.participants.c.token)).scalars().first()
    assert db.unpack(blob)["m"][0] == [0, 1, 2, "c1"]
    assert tok and not tok.startswith("tok-")              # fresh session secrets
