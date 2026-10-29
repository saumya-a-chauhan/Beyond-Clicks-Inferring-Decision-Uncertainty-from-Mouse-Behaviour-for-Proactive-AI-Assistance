"""FastAPI app: participant API, researcher (admin) API and the static website."""
import csv
import io
import json
import random
import secrets
import tempfile
import zipfile
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select

from . import analysis, auth, backup, config, datacsv, db, live, llm, phones, sheets
from .assign import next_assignment
from .defaults import CONDITIONS, DETECTOR_DEFAULTS, STUDY_INFO_DEFAULTS
from .detector import compute_ticks, popup_content
from .features import Timeline, baseline_stats
from .plans import main_plan, pilot_plan

db.init_db()


@asynccontextmanager
async def lifespan(_app):
    try:
        backup.make_backup("start")        # a copy every time the site starts
    except Exception:  # noqa: BLE001 - never block the study because of a backup
        pass
    backup.start_periodic()
    yield
    try:
        backup.checkpoint()                # hti_study.db alone is complete once the site stops
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title="Beyond Clicks study", lifespan=lifespan)
_rng = random.SystemRandom()


# ---------------------------------------------------------------- helpers
def study_info():
    return dict(STUDY_INFO_DEFAULTS, **(db.get_setting("study_info", {}) or {}))


def frozen_state():
    return db.get_setting("frozen", {"frozen": False}) or {"frozen": False}


def participant_by_token(conn, token):
    if not token:
        raise HTTPException(401, "Missing participant token")
    row = conn.execute(select(db.participants).where(db.participants.c.token == token)).first()
    if row is None:
        raise HTTPException(404, "Session not found. Please start again from the home page.")
    return dict(row._mapping)


def task_for(conn, task_id, token):
    p = participant_by_token(conn, token)
    row = conn.execute(select(db.tasks).where(db.tasks.c.id == task_id)).first()
    if row is None or row.participant_id != p["id"]:
        raise HTTPException(404, "Task not found")
    return p, dict(row._mapping)


def p_cfg(p):
    cfg = db.loads(p.get("settings_snapshot")) or analysis.detector_cfg()
    full = dict(DETECTOR_DEFAULTS)
    full.update(cfg)
    return full


def public_participant(p):
    return {"code": p["code"], "study": p["study"], "plan": db.loads(p["plan"], []),
            "step_index": p["step_index"], "status": p["status"]}


def name_of(set_id, pid):
    ph = phones.phone(set_id, pid)
    return ph["name"] if ph else pid


# ---------------------------------------------------------------- pages
@app.get("/")
def page_home():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/run")
def page_run():
    return FileResponse(config.STATIC_DIR / "run.html")


@app.get("/admin")
def page_admin():
    return FileResponse(config.STATIC_DIR / "admin.html")


@app.get("/guide")
def page_guide():
    return FileResponse(config.STATIC_DIR / "guide.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    # browsers must re-check site files, so an updated version reaches every participant laptop
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path in ("/", "/run", "/admin", "/guide"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


# ---------------------------------------------------------------- participant API
@app.get("/api/status")
def api_status():
    fz = frozen_state()
    return {"main_unlocked": bool(fz.get("frozen")), "frozen_at": fz.get("frozen_at"), "study_info": study_info(),
            "conditions": {k: v["name"] for k, v in CONDITIONS.items()}}


class NewParticipant(BaseModel):
    study: str


@app.post("/api/participants")
def api_new_participant(body: NewParticipant):
    if body.study not in ("pilot", "main"):
        raise HTTPException(400, "Unknown study")
    if body.study == "main" and not frozen_state().get("frozen"):
        raise HTTPException(403, "The main study is locked until the pilot settings are frozen.")
    with db.engine.begin() as conn:
        slot, cond_order, set_order = next_assignment(conn, body.study)
        prefix = "P" if body.study == "pilot" else "M"
        n = conn.execute(select(func.count()).select_from(db.participants)
                         .where(db.participants.c.study == body.study)).scalar() or 0
        code = f"{prefix}{n + 1:02d}"
        while conn.execute(select(db.participants.c.id).where(db.participants.c.code == code)).first():
            n += 1
            code = f"{prefix}{n + 1:02d}"
        ai_check = bool(body.study == "pilot" and db.get_setting("pilot_ai_check_next", False))
        plan = pilot_plan(set_order, ai_check) if body.study == "pilot" else main_plan(cond_order, set_order)
        token = secrets.token_urlsafe(24)
        conn.execute(db.participants.insert().values(
            code=code, token=token, study=body.study, slot=slot, condition_order=db.dumps(cond_order),
            set_order=db.dumps(set_order), pilot_ai_check=ai_check, plan=db.dumps(plan), step_index=0,
            status="started", settings_snapshot=db.dumps(analysis.detector_cfg()), excluded=False,
            simulated=False, created_at=db.now(), updated_at=db.now()))
    return {"token": token, "code": code, "plan": plan, "step_index": 0, "study": body.study}


@app.get("/api/me")
def api_me(x_token: str | None = Header(None)):
    with db.engine.connect() as conn:
        p = participant_by_token(conn, x_token)
    return public_participant(p)


class StepBody(BaseModel):
    token: str
    step_index: int
    step_key: str
    kind: str
    task_key: str | None = None
    data: dict = {}


GENDERS = ("woman", "man", "non-binary", "self-describe", "prefer-not")


@app.post("/api/step")
def api_step(body: StepBody, background: BackgroundTasks):
    with db.engine.begin() as conn:
        p = participant_by_token(conn, body.token)
        plan = db.loads(p["plan"], [])
        if body.step_index != p["step_index"] or body.step_index >= len(plan) or plan[body.step_index]["key"] != body.step_key:
            return public_participant(p)   # duplicate or stale submit: ignore
        conn.execute(db.responses.insert().values(
            participant_id=p["id"], step_key=body.step_key, kind=body.kind, task_key=body.task_key,
            data=db.dumps(body.data), created_at=db.now()))
        upd = {"step_index": p["step_index"] + 1, "updated_at": db.now()}
        if body.kind == "consent" and not body.data.get("agree"):
            upd["status"] = "declined"
            upd["step_index"] = len(plan) - 1
        if body.kind == "device_check":
            upd["device"] = db.dumps(body.data)
        if body.kind == "demographics":
            age, gender = body.data.get("age"), body.data.get("gender")
            if not isinstance(age, int) or not 18 <= age <= 100 or gender not in GENDERS:
                raise HTTPException(400, "Please enter an age of 18 or older and choose a gender option.")
        if upd["step_index"] >= len(plan) - 1 and upd.get("status") != "declined":
            upd["status"] = "completed"
        conn.execute(db.participants.update().where(db.participants.c.id == p["id"]).values(**upd))
        p.update(upd)
    if upd.get("status") == "completed":
        background.add_task(backup.make_backup, f"done_{p['code']}")
    return public_participant(p)


class TaskStart(BaseModel):
    token: str
    task_key: str
    viewport: dict = {}


@app.post("/api/task/start")
def api_task_start(body: TaskStart):
    with db.engine.begin() as conn:
        p = participant_by_token(conn, body.token)
        plan = db.loads(p["plan"], [])
        step = next((s for s in plan if s.get("kind") == "task" and s.get("task_key") == body.task_key), None)
        if step is None:
            raise HTTPException(400, "This task is not in your plan")
        row = conn.execute(select(db.tasks).where(db.tasks.c.participant_id == p["id"],
                                                  db.tasks.c.task_key == body.task_key)).first()
        offset = 0
        ended = False
        if row is None:
            ids = [ph["id"] for ph in phones.get_set(step["set"])["phones"]]
            _rng.shuffle(ids)
            res = conn.execute(db.tasks.insert().values(
                participant_id=p["id"], task_key=body.task_key, kind=step["task_kind"] if step["task_kind"] in ("main", "pilot_ai", "practice") else "baseline",
                position=step.get("position"), condition=step["condition"], set_id=step["set"],
                card_order=db.dumps(ids), viewport=db.dumps(body.viewport), started_at=db.now()))
            task_id = res.inserted_primary_key[0]
            card_order = ids
            next_seq = 0
        else:
            task_id = row.id
            ended = row.ended_at is not None
            card_order = db.loads(row.card_order, [])
            ev = db.task_events(conn, task_id)
            last = max([e[0] for e in ev["m"]] + [e[0] for e in ev["s"]] + [0])
            offset = int(last) + 500 if last else 0
            next_seq = (conn.execute(select(func.max(db.event_batches.c.seq))
                                     .where(db.event_batches.c.task_id == task_id)).scalar() or 0) + 1
    return {"task_id": task_id, "set": phones.public_set(step["set"]), "card_order": card_order,
            "condition": step["condition"], "task_kind": step["task_kind"], "time_offset_ms": offset,
            "next_seq": next_seq, "ended": ended}


class Events(BaseModel):
    token: str
    seq: int
    now: int
    m: list = []
    s: list = []
    c: list = []


def _live_loader(conn, p, t):
    def load():
        base = db.loads(p["baseline"]) or {}
        return t["condition"], db.loads(t["card_order"], []), base, p_cfg(p)
    return load


@app.post("/api/task/{task_id}/events")
def api_events(task_id: int, body: Events):
    if len(body.m) + len(body.s) + len(body.c) > 20000:
        raise HTTPException(413, "Batch too large")
    with db.engine.begin() as conn:
        p, t = task_for(conn, task_id, body.token)
        if t["ended_at"] is not None:
            return {"ok": True, "ended": True}
        dup = conn.execute(select(db.event_batches.c.id).where(db.event_batches.c.task_id == task_id,
                                                               db.event_batches.c.seq == body.seq)).first()
        if dup:
            return {"ok": True, "duplicate": True}
        conn.execute(db.event_batches.insert().values(task_id=task_id, seq=body.seq,
                                                      data=db.pack({"m": body.m, "s": body.s, "c": body.c}),
                                                      created_at=db.now()))
    if t["condition"] not in ("C3", "C4"):
        return {"ok": True}
    lt, rebuilt = live.get(task_id, _live_loader(None, p, t))
    with lt.lock:
        if not rebuilt:
            lt.add(body.m, body.s)
        fired = lt.process(int(body.now))
    if fired is None:
        return {"ok": True}
    content = popup_content(fired, live.MODE[t["condition"]], rng=random.Random(task_id * 1000 + len(lt.rule.fired)))
    pair = content["pair"] or db.loads(t["card_order"], [])[:2]
    spec = content["spec"] or (phones.get_set(t["set_id"])["card"].get("priorities") or ["battery"])[0]
    with db.engine.begin() as conn:
        res = conn.execute(db.popups.insert().values(
            task_id=task_id, t_ms=fired["t"], source=live.MODE[t["condition"]],
            predicted_type=content["predicted_type"], pair=db.dumps(pair), spec=spec,
            score=fired["scores"]["avg"], zs=db.dumps(fired["z"])))
        pop_id = res.inserted_primary_key[0]
    labels = phones.catalog()["spec_labels"]
    return {"ok": True, "popup": {
        "id": pop_id, "predicted_type": content["predicted_type"],
        "pair": [{"id": x, "name": name_of(t["set_id"], x)} for x in pair],
        "spec": {"key": spec, "label": labels.get(spec, spec)}}}


class TaskEnd(BaseModel):
    token: str
    chosen: str
    decision_ms: int


def _finish_task_background(task_id):
    """After a task: per-person baseline (after baseline2) or offline ticks (shopping tasks)."""
    with db.engine.connect() as conn:
        t = dict(conn.execute(select(db.tasks).where(db.tasks.c.id == task_id)).first()._mapping)
        p = dict(conn.execute(select(db.participants).where(db.participants.c.id == t["participant_id"])).first()._mapping)
        cfg = p_cfg(p)
        if t["task_key"] == "baseline2":
            tls = []
            for k in ("baseline1", "baseline2"):
                r = conn.execute(select(db.tasks).where(db.tasks.c.participant_id == p["id"], db.tasks.c.task_key == k)).first()
                if r is None:
                    continue
                ev = db.task_events(conn, r.id)
                if ev["m"]:
                    tls.append((Timeline(ev["m"], ev["s"]), int(r.decision_ms or max(e[0] for e in ev["m"]))))
            base = baseline_stats(tls, cfg) if tls else {}
            with db.engine.begin() as w:
                w.execute(db.participants.update().where(db.participants.c.id == p["id"]).values(baseline=db.dumps(base)))
            return
        if t["kind"] not in ("main", "pilot_ai"):
            return
        base = db.loads(p["baseline"]) or {}
        ev = db.task_events(conn, task_id)
    ticks = compute_ticks(ev["m"], ev["s"], db.loads(t["card_order"], []), base, cfg, int(t["decision_ms"] or 0))
    slim = [{"t": tk["t"], "raw": tk["raw"], "z": tk["z"], "scores": tk["scores"], "seen": tk["seen"]} for tk in ticks]
    with db.engine.begin() as w:
        w.execute(db.tasks.update().where(db.tasks.c.id == task_id).values(ticks=db.pack(slim)))


@app.post("/api/task/{task_id}/end")
def api_task_end(task_id: int, body: TaskEnd, bg: BackgroundTasks):
    with db.engine.begin() as conn:
        p, t = task_for(conn, task_id, body.token)
        if t["ended_at"] is None:
            correct, rank = phones.score_choice(t["set_id"], body.chosen, t["task_key"] if t["set_id"] == "P" else t["kind"])
            conn.execute(db.tasks.update().where(db.tasks.c.id == task_id).values(
                ended_at=db.now(), decision_ms=body.decision_ms, chosen=body.chosen, correct=correct, rank=rank,
                final_choice=body.chosen, final_correct=correct, final_rank=rank, switched=False))
    live.drop(task_id)
    bg.add_task(_finish_task_background, task_id)
    return {"ok": True}


class SwitchBody(BaseModel):
    token: str
    final_choice: str


@app.post("/api/task/{task_id}/switch")
def api_switch(task_id: int, body: SwitchBody):
    with db.engine.begin() as conn:
        p, t = task_for(conn, task_id, body.token)
        correct, rank = phones.score_choice(t["set_id"], body.final_choice, t["kind"])
        conn.execute(db.tasks.update().where(db.tasks.c.id == task_id).values(
            final_choice=body.final_choice, final_correct=correct, final_rank=rank,
            switched=body.final_choice != t["chosen"]))
    return {"ok": True}


class PopupAnswer(BaseModel):
    token: str
    t: int
    answer: str | None = None
    choice: str | None = None
    pair: list | None = None
    spec: str | None = None


def _popup_for(conn, popup_id, token):
    row = conn.execute(select(db.popups).where(db.popups.c.id == popup_id)).first()
    if row is None:
        raise HTTPException(404, "Pop-up not found")
    p, t = task_for(conn, row.task_id, token)
    return p, t, dict(row._mapping)


@app.post("/api/popup/{popup_id}/unsure")
def api_popup_unsure(popup_id: int, body: PopupAnswer):
    if body.answer not in ("yes", "no"):
        raise HTTPException(400, "answer must be yes or no")
    with db.engine.begin() as conn:
        _popup_for(conn, popup_id, body.token)
        conn.execute(db.popups.update().where(db.popups.c.id == popup_id).values(unsure_answer=body.answer, unsure_ms=body.t))
    return {"ok": True}


@app.post("/api/popup/{popup_id}/choice")
def api_popup_choice(popup_id: int, body: PopupAnswer):
    if body.choice not in ("compare", "explain", "general", "dismiss"):
        raise HTTPException(400, "bad choice")
    with db.engine.begin() as conn:
        p, t, pop = _popup_for(conn, popup_id, body.token)
        conn.execute(db.popups.update().where(db.popups.c.id == popup_id).values(choice=body.choice, choice_ms=body.t))
    if body.choice == "dismiss":
        lt = live._tasks.get(t["id"])
        if lt:
            lt.popup_closed(True)
        with db.engine.begin() as conn:
            conn.execute(db.popups.update().where(db.popups.c.id == popup_id).values(closed_ms=body.t))
        return {"ok": True}
    args = {"pair": body.pair or db.loads(pop["pair"], [])} if body.choice == "compare" else \
           {"spec": body.spec or pop["spec"]} if body.choice == "explain" else {}
    return _ai(t, body.choice, args, body.t, "popup", popup_id)


def _ai(t, mode, args, t_ms, origin, popup_id=None):
    out = llm.answer(t["set_id"], mode, args)
    with db.engine.begin() as conn:
        conn.execute(db.ai_requests.insert().values(
            task_id=t["id"], popup_id=popup_id, t_ms=t_ms, origin=origin, mode=mode, args=llm.args_json(args),
            provider=out["provider"], model=out["model"], response=out["text"], latency_ms=out["latency_ms"],
            error=out["error"]))
    return {"ok": True, "text": out["text"], "provider": out["provider"]}


@app.post("/api/popup/{popup_id}/closed")
def api_popup_closed(popup_id: int, body: PopupAnswer):
    with db.engine.begin() as conn:
        p, t, pop = _popup_for(conn, popup_id, body.token)
        if pop["closed_ms"] is None:
            conn.execute(db.popups.update().where(db.popups.c.id == popup_id).values(closed_ms=body.t))
    lt = live._tasks.get(t["id"])
    if lt:
        lt.popup_closed(False)
    return {"ok": True}


class AskBody(BaseModel):
    token: str
    t: int
    mode: str
    pair: list | None = None
    spec: str | None = None
    question: str | None = None


@app.post("/api/task/{task_id}/ask")
def api_ask(task_id: int, body: AskBody):
    with db.engine.connect() as conn:
        p, t = task_for(conn, task_id, body.token)
    if t["condition"] not in ("C2", "DEMO"):
        raise HTTPException(403, "Ask AI is not available in this round")
    if body.mode not in ("compare", "explain", "ask", "general"):
        raise HTTPException(400, "bad mode")
    args = {"pair": body.pair} if body.mode == "compare" else {"spec": body.spec} if body.mode == "explain" else \
           {"question": (body.question or "")[:400]} if body.mode == "ask" else {}
    return _ai(t, body.mode, args, body.t, "ask")


@app.get("/api/task/{task_id}/replay")
def api_replay(task_id: int, x_token: str | None = Header(None)):
    with db.engine.connect() as conn:
        p, t = task_for(conn, task_id, x_token)
        if p["study"] != "pilot" or t["kind"] != "main":
            raise HTTPException(403, "Replay is only for pilot shopping tasks")
        ev = db.task_events(conn, task_id)
    return {"task_id": task_id, "set": phones.public_set(t["set_id"]), "card_order": db.loads(t["card_order"], []),
            "viewport": db.loads(t["viewport"], {}), "decision_ms": t["decision_ms"], "events": ev}


@app.get("/api/task/by-key/{task_key}")
def api_task_by_key(task_key: str, x_token: str | None = Header(None)):
    with db.engine.connect() as conn:
        p = participant_by_token(conn, x_token)
        row = conn.execute(select(db.tasks.c.id, db.tasks.c.chosen, db.tasks.c.set_id, db.tasks.c.card_order)
                           .where(db.tasks.c.participant_id == p["id"], db.tasks.c.task_key == task_key)).first()
    if row is None:
        raise HTTPException(404, "Task not found")
    return {"task_id": row.id, "chosen": row.chosen, "set": phones.public_set(row.set_id),
            "card_order": db.loads(row.card_order, [])}


class LabelsBody(BaseModel):
    token: str
    intervals: list
    replay_speed: float = 1.0


@app.post("/api/task/{task_id}/labels")
def api_labels(task_id: int, body: LabelsBody):
    clean = []
    for iv in body.intervals:
        if isinstance(iv, (list, tuple)) and len(iv) == 2:
            a, b = float(iv[0]), float(iv[1])
            if b > a >= 0:
                clean.append([int(a), int(b)])
    with db.engine.begin() as conn:
        task_for(conn, task_id, body.token)
        conn.execute(db.labels.delete().where(db.labels.c.task_id == task_id))
        conn.execute(db.labels.insert().values(task_id=task_id, intervals=db.dumps(clean),
                                               replay_speed=body.replay_speed, created_at=db.now()))
    return {"ok": True, "n": len(clean)}


class TokenBody(BaseModel):
    token: str


@app.post("/api/delete-my-data")
def api_delete_my_data(body: TokenBody):
    with db.engine.begin() as conn:
        p = participant_by_token(conn, body.token)
        _delete_participant(conn, p["id"])
        db.log_audit("participant_deleted_self", {"code": p["code"]}, conn=conn)
    return {"ok": True}


def _delete_participant(conn, pid):
    tids = [r[0] for r in conn.execute(select(db.tasks.c.id).where(db.tasks.c.participant_id == pid))]
    for tbl in (db.event_batches, db.popups, db.ai_requests, db.labels):
        if tids:
            conn.execute(tbl.delete().where(tbl.c.task_id.in_(tids)))
    conn.execute(db.tasks.delete().where(db.tasks.c.participant_id == pid))
    conn.execute(db.responses.delete().where(db.responses.c.participant_id == pid))
    conn.execute(db.participants.delete().where(db.participants.c.id == pid))


# ---------------------------------------------------------------- researcher API
class Login(BaseModel):
    password: str


@app.post("/api/admin/login")
def admin_login(body: Login, response: Response, request: Request):
    if not config.ADMIN_PASSWORD:
        raise HTTPException(503, "ADMIN_PASSWORD is not set on the server")
    if not auth.check_password(body.password):
        raise HTTPException(401, "Wrong password")
    response.set_cookie(auth.COOKIE, auth.make_token(), max_age=auth.TTL_S, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https")
    return {"ok": True}


@app.post("/api/admin/logout")
def admin_logout(response: Response):
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@app.get("/api/admin/overview", dependencies=[Depends(auth.require_admin)])
def admin_overview():
    with db.engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(select(
            db.participants.c.study, db.participants.c.status, db.participants.c.simulated, db.participants.c.excluded))]
        audit_rows = [dict(r._mapping) for r in conn.execute(select(db.audit).order_by(db.audit.c.id.desc()).limit(50))]
    counts = {}
    for r in rows:
        key = f"{r['study']}{' (simulated)' if r['simulated'] else ''}"
        counts.setdefault(key, {"started": 0, "completed": 0, "declined": 0, "excluded": 0})
        counts[key][r["status"] if r["status"] in ("started", "completed", "declined") else "started"] += 1
        if r["excluded"]:
            counts[key]["excluded"] += 1
    return {"counts": counts, "frozen": frozen_state(), "detector": analysis.detector_cfg(),
            "study_info": study_info(), "pilot_ai_check_next": bool(db.get_setting("pilot_ai_check_next", False)),
            "audit": [{"ts": str(a["ts"]), "action": a["action"], "detail": db.loads(a["detail"])} for a in audit_rows],
            "llm": {"gemini_key": bool(config.GEMINI_API_KEY), "groq_key": bool(config.GROQ_API_KEY),
                    "gemini_model": config.GEMINI_MODEL, "groq_model": config.GROQ_MODEL},
            "database": "postgres" if config.DATABASE_URL.startswith("postgresql") else "sqlite",
            "site_name": sheets.site_name(), "backups": backup.list_backups()[:5],
            "backup_dir": str(backup.BACKUP_DIR) if backup.db_path() else None,
            "db_file": str(backup.db_path()) if backup.db_path() else None}


@app.get("/api/admin/participants", dependencies=[Depends(auth.require_admin)])
def admin_participants():
    with db.engine.connect() as conn:
        ps = [dict(r._mapping) for r in conn.execute(select(db.participants).order_by(db.participants.c.id))]
        tasks = [dict(r._mapping) for r in conn.execute(select(
            db.tasks.c.participant_id, db.tasks.c.task_key, db.tasks.c.condition, db.tasks.c.correct,
            db.tasks.c.decision_ms, db.tasks.c.set_id))]
        demo = {r.participant_id: db.loads(r.data, {}) or {} for r in conn.execute(
            select(db.responses.c.participant_id, db.responses.c.data).where(db.responses.c.kind == "demographics"))}
        nlab = dict(conn.execute(select(db.tasks.c.participant_id, func.count(db.labels.c.id))
                                 .join(db.labels, db.labels.c.task_id == db.tasks.c.id)
                                 .group_by(db.tasks.c.participant_id)).all())
    by_p = {}
    for t in tasks:
        by_p.setdefault(t["participant_id"], []).append(t)
    out = []
    for p in ps:
        plan = db.loads(p["plan"], [])
        out.append({"id": p["id"], "code": p["code"], "study": p["study"], "status": p["status"],
                    "step": f"{min(p['step_index'] + 1, len(plan))}/{len(plan)}",
                    "current": plan[p["step_index"]]["key"] if p["step_index"] < len(plan) else "",
                    "condition_order": db.loads(p["condition_order"]), "set_order": db.loads(p["set_order"]),
                    "pilot_ai_check": p["pilot_ai_check"], "excluded": p["excluded"], "simulated": p["simulated"],
                    "notes": p["notes"], "created_at": str(p["created_at"]), "labels": nlab.get(p["id"], 0),
                    "device": db.loads(p["device"]),
                    "age": demo.get(p["id"], {}).get("age"),
                    "gender": (demo.get(p["id"], {}).get("gender_self") or "self-describe")
                    if demo.get(p["id"], {}).get("gender") == "self-describe" else demo.get(p["id"], {}).get("gender"),
                    "tasks": sorted([{"key": t["task_key"], "cond": t["condition"], "set": t["set_id"],
                                      "correct": t["correct"], "time_s": (t["decision_ms"] or 0) / 1000}
                                     for t in by_p.get(p["id"], [])], key=lambda x: x["key"])})
    return out


class ExcludeBody(BaseModel):
    excluded: bool
    note: str = ""


@app.post("/api/admin/participants/{pid}/exclude", dependencies=[Depends(auth.require_admin)])
def admin_exclude(pid: int, body: ExcludeBody):
    with db.engine.begin() as conn:
        conn.execute(db.participants.update().where(db.participants.c.id == pid)
                     .values(excluded=body.excluded, notes=body.note))
        db.log_audit("exclude" if body.excluded else "include", {"participant": pid, "note": body.note}, conn=conn)
    return {"ok": True}


@app.delete("/api/admin/participants/{pid}", dependencies=[Depends(auth.require_admin)])
def admin_delete(pid: int):
    backup.make_backup("before_delete")
    with db.engine.begin() as conn:
        row = conn.execute(select(db.participants.c.code).where(db.participants.c.id == pid)).first()
        _delete_participant(conn, pid)
        db.log_audit("participant_deleted", {"code": row[0] if row else pid}, conn=conn)
    return {"ok": True}


@app.post("/api/admin/delete-simulated", dependencies=[Depends(auth.require_admin)])
def admin_delete_sim():
    backup.make_backup("before_delete")
    with db.engine.begin() as conn:
        ids = [r[0] for r in conn.execute(select(db.participants.c.id).where(db.participants.c.simulated.is_(True)))]
        for pid in ids:
            _delete_participant(conn, pid)
        db.log_audit("simulated_deleted", {"n": len(ids)}, conn=conn)
    return {"ok": True, "deleted": len(ids)}


class ClearBody(BaseModel):
    confirm: str


# Settings that describe the laptop and the consent page, not the data: kept when all study data is cleared.
KEEP_ON_CLEAR = ("study_info", "site_name")


@app.post("/api/admin/clear-all", dependencies=[Depends(auth.require_admin)])
def admin_clear_all(body: ClearBody):
    """Deletes every participant and everything recorded, and the pilot analysis, freeze and detector settings.
    A backup is saved first; the audit log is kept."""
    if body.confirm != "DELETE ALL":
        raise HTTPException(400, 'Type DELETE ALL to confirm.')
    path = backup.make_backup("before_clear_all")
    with db.engine.begin() as conn:
        n = conn.execute(select(func.count()).select_from(db.participants)).scalar() or 0
        for tbl in (db.event_batches, db.popups, db.ai_requests, db.labels, db.tasks, db.responses, db.participants):
            conn.execute(tbl.delete())
        conn.execute(db.settings_t.delete().where(db.settings_t.c.key.not_in(KEEP_ON_CLEAR)))
        db.log_audit("all_data_cleared", {"participants": n, "backup": path.name if path else None}, conn=conn)
    live._tasks.clear()
    return {"ok": True, "deleted": n, "backup": path.name if path else None}


class SettingsBody(BaseModel):
    study_info: dict | None = None
    detector: dict | None = None
    pilot_ai_check_next: bool | None = None
    site_name: str | None = None


@app.post("/api/admin/settings", dependencies=[Depends(auth.require_admin)])
def admin_settings(body: SettingsBody):
    if body.study_info is not None:
        db.set_setting("study_info", {k: str(v) for k, v in body.study_info.items() if k in STUDY_INFO_DEFAULTS})
    if body.pilot_ai_check_next is not None:
        db.set_setting("pilot_ai_check_next", bool(body.pilot_ai_check_next))
    if body.site_name is not None:
        db.set_setting("site_name", body.site_name.strip()[:64])
    if body.detector is not None:
        if frozen_state().get("frozen"):
            raise HTTPException(409, "Settings are frozen. Unfreeze (logged) before changing them.")
        cur = db.get_setting("detector", {}) or {}
        for k, v in body.detector.items():
            if k in DETECTOR_DEFAULTS:
                cur[k] = v
        db.set_setting("detector", cur)
        db.log_audit("detector_edit", body.detector)
    return {"ok": True}


class SimBody(BaseModel):
    include_simulated: bool = False


@app.post("/api/admin/pilot-analysis", dependencies=[Depends(auth.require_admin)])
def admin_pilot_analysis(body: SimBody):
    res = analysis.pilot_analysis(include_sim=body.include_simulated)
    db.set_setting("pilot_analysis_last", {"proposal": res.get("proposal"), "n_people": res.get("n_people"),
                                           "n_tasks": res.get("n_tasks"), "include_simulated": body.include_simulated,
                                           "chosen": res.get("chosen"), "loo_avg": (res.get("loo") or {}).get("avg")})
    return JSONResponse(json.loads(json.dumps(res, default=str)))


@app.post("/api/admin/main-results", dependencies=[Depends(auth.require_admin)])
def admin_main_results(body: SimBody):
    return JSONResponse(json.loads(json.dumps(analysis.main_results(include_sim=body.include_simulated), default=str)))


class FreezeBody(BaseModel):
    threshold: float | None = None
    note: str = ""


@app.post("/api/admin/freeze", dependencies=[Depends(auth.require_admin)])
def admin_freeze(body: FreezeBody):
    if frozen_state().get("frozen"):
        raise HTTPException(409, "Already frozen")
    last = db.get_setting("pilot_analysis_last")
    if not last or not last.get("proposal"):
        raise HTTPException(400, "Run the pilot analysis first")
    prop = last["proposal"]
    thr = body.threshold if body.threshold is not None else prop.get("threshold")
    if thr is None:
        raise HTTPException(400, "No threshold passed the rule. Enter one manually with a note explaining why.")
    if body.threshold is not None and prop.get("threshold") is not None and abs(body.threshold - prop["threshold"]) > 1e-9 and not body.note.strip():
        raise HTTPException(400, "You chose a threshold different from the rule's proposal: a note is required.")
    cur = db.get_setting("detector", {}) or {}
    cur["threshold"] = float(thr)
    if prop.get("min_spread"):
        cur["min_spread"] = prop["min_spread"]
    if prop.get("c4_rate_per_min"):
        cur["c4_rate_per_min"] = prop["c4_rate_per_min"]
    db.set_setting("detector", cur)
    state = {"frozen": True, "frozen_at": str(db.now()), "threshold": float(thr), "note": body.note,
             "proposal": prop, "pilot_people": last.get("n_people"), "pilot_tasks": last.get("n_tasks"),
             "include_simulated": last.get("include_simulated"), "settings": analysis.detector_cfg()}
    db.set_setting("frozen", state)
    db.log_audit("freeze", state)
    backup.make_backup("freeze")
    return state


class UnfreezeBody(BaseModel):
    reason: str


@app.post("/api/admin/unfreeze", dependencies=[Depends(auth.require_admin)])
def admin_unfreeze(body: UnfreezeBody):
    if not body.reason.strip():
        raise HTTPException(400, "A reason is required; it is kept in the audit log.")
    db.set_setting("frozen", {"frozen": False})
    db.log_audit("unfreeze", {"reason": body.reason})
    return {"ok": True}


@app.post("/api/admin/llm-test", dependencies=[Depends(auth.require_admin)])
def admin_llm_test():
    return llm.provider_check()


def _csv(rows, cols):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c) for c in cols])
    return buf.getvalue()


@app.get("/api/admin/export.zip", dependencies=[Depends(auth.require_admin)])
def admin_export():
    tmp = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z, db.engine.connect() as conn:
        ps = [dict(r._mapping) for r in conn.execute(select(db.participants))]
        codes = {p["id"]: p["code"] for p in ps}
        for p in ps:
            p.pop("token", None)
        z.writestr("participants.csv", _csv(ps, [c.name for c in db.participants.columns if c.name != "token"]))
        tasks = [dict(r._mapping) for r in conn.execute(select(db.tasks))]
        tcode = {t["id"]: (codes.get(t["participant_id"]), t["task_key"]) for t in tasks}
        tcols = [c.name for c in db.tasks.columns if c.name != "ticks"]
        for t in tasks:
            t["participant"] = codes.get(t["participant_id"])
        z.writestr("tasks.csv", _csv(tasks, ["participant"] + tcols))
        for name, tbl in (("popups", db.popups), ("ai_requests", db.ai_requests), ("labels", db.labels)):
            rows = [dict(r._mapping) for r in conn.execute(select(tbl))]
            for r in rows:
                pc, tk = tcode.get(r["task_id"], (None, None))
                r["participant"], r["task_key"] = pc, tk
            z.writestr(f"{name}.csv", _csv(rows, ["participant", "task_key"] + [c.name for c in tbl.columns]))
        rows = [dict(r._mapping) for r in conn.execute(select(db.responses))]
        for r in rows:
            r["participant"] = codes.get(r["participant_id"])
        z.writestr("responses.csv", _csv(rows, ["participant"] + [c.name for c in db.responses.columns]))
        for t in tasks:
            pc, tk = tcode[t["id"]]
            ev = db.task_events(conn, t["id"])
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["t_ms", "type", "x", "y", "scroll_y", "zone", "label"])
            for e in ev["m"]:
                w.writerow([e[0], "move", e[1], e[2], "", e[3], ""])
            for e in ev["s"]:
                w.writerow([e[0], "scroll", "", "", e[1], e[2], ""])
            for e in ev["c"]:
                w.writerow([e[0], "click", e[1], e[2], "", e[3], e[4] if len(e) > 4 else ""])
            z.writestr(f"events/{pc}_{tk}.csv", buf.getvalue())
            tks = db.unpack(conn.execute(select(db.tasks.c.ticks).where(db.tasks.c.id == t["id"])).scalar(), [])
            if tks:
                buf = io.StringIO()
                w = csv.writer(buf)
                head = ["t_ms", "seen"] + [f"raw_{s}" for s in "BFIWS"] + [f"z_{s}" for s in "BFIWS"] + ["score_avg", "score_max", "score_B", "score_I"]
                w.writerow(head)
                for tk in tks:
                    w.writerow([tk["t"], tk["seen"]] + [tk["raw"][s] for s in "BFIWS"] + [round(tk["z"][s], 4) for s in "BFIWS"]
                               + [round(tk["scores"][k], 4) for k in ("avg", "max", "B", "I")])
                z.writestr(f"ticks/{pc}_{tk}.csv", buf.getvalue())
        st_rows = [dict(r._mapping) for r in conn.execute(select(db.settings_t))]
        z.writestr("settings.json", json.dumps({r["key"]: db.loads(r["value"]) for r in st_rows}, indent=2, default=str))
        au = [dict(r._mapping) for r in conn.execute(select(db.audit))]
        z.writestr("audit.csv", _csv(au, ["id", "ts", "action", "detail"]))
        z.writestr("README.txt", "See docs/DATA_DICTIONARY.md in the project repository for every column.\n")
    tmp.seek(0)
    return StreamingResponse(tmp, media_type="application/zip",
                             headers={"Content-Disposition": "attachment; filename=hti_study_export.zip"})


# ---------------------------------------------------------------- results sheet (Excel), study-data CSV, backups
def _flag(v):
    return str(v).lower() in ("1", "true", "yes", "on")


@app.get("/api/admin/sheet", dependencies=[Depends(auth.require_admin)])
def admin_sheet(study: str = "pilot", include_sim: str = "0"):
    if study not in sheets.STUDIES:
        raise HTTPException(400, "Unknown study")
    return {"columns": sheets.display_columns(), "rows": sheets.local_rows(study, _flag(include_sim)),
            "meanings": dict(sheets.COLUMNS), "loaded": db.get_setting("loaded_data")}


@app.get("/api/admin/export.xlsx", dependencies=[Depends(auth.require_admin)])
def admin_export_xlsx(include_sim: str = "0", include_mouse: str = "0"):
    data = sheets.to_xlsx(_flag(include_sim), _flag(include_mouse))
    name = f"beyond_clicks_results_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/admin/data.csv", dependencies=[Depends(auth.require_admin)])
def admin_data_csv():
    data = datacsv.export_csv(sheets.site_name())
    name = f"beyond_clicks_study_data_{sheets.site_name()}_{datetime.now():%Y%m%d_%H%M}.csv".replace(" ", "_")
    return Response(data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/admin/data.csv", dependencies=[Depends(auth.require_admin)])
async def admin_load_data_csv(request: Request, filename: str = "study_data.csv"):
    content = await request.body()
    if not content:
        raise HTTPException(400, "The file is empty.")
    try:
        datacsv._parse(content)                 # check the whole file before touching anything
    except (ValueError, UnicodeDecodeError) as e:
        raise HTTPException(400, str(e) if isinstance(e, ValueError) else "The file is not a UTF-8 CSV.") from e
    backup.make_backup("before_csv_load")
    return datacsv.load_csv(content, Path(filename).name)


@app.get("/api/admin/backups", dependencies=[Depends(auth.require_admin)])
def admin_backups():
    return {"backups": backup.list_backups(), "folder": str(backup.BACKUP_DIR) if backup.db_path() else None}


@app.post("/api/admin/backups", dependencies=[Depends(auth.require_admin)])
def admin_backup_now():
    f = backup.make_backup("manual")
    if f is None:
        raise HTTPException(400, "Backups are only for the local database.")
    return {"ok": True, "name": f.name}


@app.get("/api/admin/backup.db", dependencies=[Depends(auth.require_admin)])
def admin_backup_download():
    if backup.db_path() is None:
        raise HTTPException(400, "Backups are only for the local database.")
    tmp_dir = Path(tempfile.mkdtemp())
    tmp = tmp_dir / "hti_study.db"
    backup.fresh_copy(tmp)
    data = tmp.read_bytes()
    tmp.unlink(missing_ok=True)
    tmp_dir.rmdir()
    name = f"hti_study_full_backup_{datetime.now():%Y%m%d_%H%M}.db"
    return Response(data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename={name}"})
