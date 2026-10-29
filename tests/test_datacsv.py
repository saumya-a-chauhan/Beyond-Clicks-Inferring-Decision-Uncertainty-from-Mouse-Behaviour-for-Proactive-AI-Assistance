"""Pilot / Main CSVs: everything survives download -> upload, an upload replaces only its own study, and wrong or
broken files are refused before anything changes."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_pytest.db")
if os.environ["DATABASE_URL"] == "sqlite:///./_pytest.db" and os.path.exists("_pytest.db"):
    os.remove("_pytest.db")                                # start from an empty test database every run

import pytest  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import datacsv, db  # noqa: E402

MOVES = [[i * 16, 100 + i, 200, "card:S1A"] for i in range(50)]


def _add_person(code, study="pilot"):
    with db.engine.begin() as c:
        pid = c.execute(db.participants.insert().values(code=code, token=f"tok-{code}", study=study, status="started",
                                                        created_at=db.now(), updated_at=db.now())).inserted_primary_key[0]
        tid = c.execute(db.tasks.insert().values(participant_id=pid, task_key="t1", kind="main", position=1,
                                                 condition="C1", set_id="S1", started_at=db.now(),
                                                 ticks=db.pack([{"t": 500}]))).inserted_primary_key[0]
        c.execute(db.event_batches.insert().values(task_id=tid, seq=0, data=db.pack({"m": MOVES, "s": [], "c": [
            [400, 120, 210, "card:S1A", "details:S1A"]]}), created_at=db.now()))
        pop = c.execute(db.popups.insert().values(task_id=tid, t_ms=300, source="detector")).inserted_primary_key[0]
        c.execute(db.ai_requests.insert().values(task_id=tid, popup_id=pop, t_ms=320, origin="popup", mode="compare"))
        c.execute(db.responses.insert().values(participant_id=pid, step_key="about", kind="demographics",
                                               data='{"age": 22, "gender": "woman"}', created_at=db.now()))


def _people(study):
    with db.engine.connect() as c:
        return sorted(r.code for r in c.execute(select(db.participants.c.code).where(db.participants.c.study == study)))


def _events(code):
    with db.engine.connect() as c:
        pid = c.execute(select(db.participants.c.id).where(db.participants.c.code == code)).scalar()
        tid = c.execute(select(db.tasks.c.id).where(db.tasks.c.participant_id == pid)).scalar()
        return db.task_events(c, tid)


def test_pilot_and_main_files(monkeypatch):
    db.init_db()
    _add_person("P01")
    _add_person("M01", "main")
    db.set_setting("frozen", {"frozen": True, "threshold": 1.75})
    monkeypatch.setattr(datacsv, "CHUNK", 200)            # force long rows to be split over several lines
    pilot = datacsv.export_csv("laptop-A", "pilot")
    main = datacsv.export_csv("laptop-A", "main")
    assert b'"token"' not in pilot
    assert b"\nmouse,P01,pilot,t1,1,0,move,100,200,,card:S1A,," in pilot      # readable mouse lines
    assert pilot.count(b"\nmouse,") == 51 and b"M01" not in pilot and b"P01" not in main
    ev_p01 = _events("P01")

    # refused files change nothing
    for bad in (b"PK\x03\x04\x14\x00\x00\x00\x08\x00\xfd", b"\xfd\xfe not utf8", b"a,b\n1,2\n", pilot[: len(pilot) // 2]):
        with pytest.raises(ValueError):
            datacsv.load_csv(bad, "bad.csv", "pilot")
    with pytest.raises(ValueError, match="main CSV"):
        datacsv.load_csv(main, "main.csv", "pilot")       # main file on the pilot button
    assert _people("pilot") == ["P01"] and _people("main") == ["M01"]

    # the receiving laptop has its own data in both studies
    _add_person("P02")
    _add_person("M02", "main")
    db.set_setting("frozen", {"frozen": True, "threshold": 9.9})
    db.set_setting("site_name", "laptop-B")
    info = datacsv.load_csv(pilot, "pilot.csv", "pilot")
    assert info["counts"]["mouse_events"] == 51
    assert _people("pilot") == ["P01"]                    # pilot replaced (P02 gone) ...
    assert _people("main") == ["M01", "M02"]              # ... main untouched
    assert db.get_setting("frozen")["threshold"] == 1.75   # the file's freeze
    assert db.get_setting("site_name") == "laptop-B"      # the laptop name stays
    assert _events("P01") == ev_p01                       # mouse data identical

    datacsv.load_csv(main, "main.csv", "main")
    assert _people("main") == ["M01"] and _people("pilot") == ["P01"]
    assert db.get_setting("loaded_data")["pilot"]["filename"] == "pilot.csv"
    with db.engine.connect() as c:
        tok = c.execute(select(db.participants.c.token)).scalars().first()
        req = c.execute(select(db.ai_requests.c.popup_id)).scalars().all()
        pops = c.execute(select(db.popups.c.id)).scalars().all()
    assert tok and not tok.startswith("tok-")              # fresh session secrets
    assert sorted(req) == sorted(pops)                      # links between rows kept after renumbering
