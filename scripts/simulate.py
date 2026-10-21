"""Simulated participants, for TESTING the whole pipeline before real data exists.

It drives the real API in-process (same code paths as the website) and generates synthetic cursor
movement with built-in "hesitation episodes" (back-and-forth between two phones, resting on a
spec, pausing in empty space). Pilot participants also produce replay labels for those episodes,
so the pilot analysis, freeze and main-study results can be tried end to end.

All simulated participants are flagged `simulated=True`; analyses exclude them unless you tick
"include simulated". Delete them in the dashboard (Export & tools) before the real study.

Usage (from the project folder):
    .venv/Scripts/python scripts/simulate.py --pilot 10
    .venv/Scripts/python scripts/simulate.py --freeze          # run pilot analysis on simulated data and freeze
    .venv/Scripts/python scripts/simulate.py --main 24
"""
import argparse
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LLM_DISABLED", "1")     # use the written fallback answers, not the API quota

from fastapi.testclient import TestClient  # noqa: E402

from app import analysis, db, main as appmain  # noqa: E402

VIEW_W, VIEW_H = 1400, 900
CARD_X0, CARD_W, GAP = 40, 318, 16
CARD_Y0, CARD_Y1 = 170, 760
SPEC_Y0, SPEC_H = 300, 52
SPECS = ["price", "battery", "chip", "display", "camera", "storage"]


def card_box(i):
    x0 = CARD_X0 + i * (CARD_W + GAP)
    return x0, x0 + CARD_W


def zone_at(x, y, order):
    if 70 <= y < 160:
        return "read:card"
    if 780 <= y < 900:
        return "read:details"
    for i, pid in enumerate(order):
        x0, x1 = card_box(i)
        if x0 <= x < x1 and CARD_Y0 <= y < CARD_Y1:
            k = int((y - SPEC_Y0) // SPEC_H)
            if 0 <= k < len(SPECS) and y >= SPEC_Y0:
                return f"spec:{pid}:{SPECS[k]}"
            return f"card:{pid}"
    return "empty"


class Path:
    """Builds a synthetic cursor trace."""

    def __init__(self, order, rng):
        self.order, self.rng = order, rng
        self.t, self.x, self.y = 0, 700.0, 120.0
        self.m, self.s = [], []
        self.scroll = 0

    def move(self, x1, y1, dur, curve=0.1, jitter=1.0):
        n = max(2, int(dur / 16))
        x0, y0 = self.x, self.y
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        bend = curve * L * (1 if self.rng.random() < 0.5 else -1)
        for k in range(1, n + 1):
            u = k / n
            s = u * u * (3 - 2 * u)
            off = bend * 4 * s * (1 - s)
            px = x0 + dx * s + nx * off + self.rng.gauss(0, jitter)
            py = y0 + dy * s + ny * off + self.rng.gauss(0, jitter)
            self.t += 16
            self.m.append([self.t, int(px), int(py), zone_at(px, py, self.order)])
        self.x, self.y = x1, y1

    def rest(self, dur):
        self.t += int(dur)

    def scroll_by(self, dy):
        self.t += 30
        self.scroll = max(0, self.scroll + dy)
        self.s.append([self.t, self.scroll, zone_at(self.x, self.y, self.order)])

    def card_point(self, i, spec=None):
        x0, x1 = card_box(i)
        x = self.rng.uniform(x0 + 30, x1 - 30)
        if spec is None:
            y = self.rng.uniform(190, 290)
        else:
            k = SPECS.index(spec)
            y = SPEC_Y0 + k * SPEC_H + self.rng.uniform(10, SPEC_H - 10)
        return x, y


def make_task(order, rng, hesitant=True, n_episodes=None, calm_factor=1.0):
    """Returns (path, episodes [[start,end]], t_end, buy_index)."""
    p = Path(order, rng)
    p.move(700, 110, 300)
    p.rest(rng.uniform(1500, 3500) * calm_factor)          # read the card
    for i in range(4):                                     # explore every phone
        x, y = p.card_point(i)
        p.move(x, y, rng.uniform(350, 600), curve=0.05)
        for _ in range(rng.randint(2, 4)):
            sx, sy = p.card_point(i, rng.choice(SPECS))
            p.move(sx, sy, rng.uniform(150, 300), curve=0.03)
            p.rest(rng.uniform(250, 700) * calm_factor)
    episodes = []
    k = n_episodes if n_episodes is not None else (rng.randint(1, 3) if hesitant else rng.randint(0, 1))
    a, b = rng.sample(range(4), 2)
    for _ in range(k):
        # calm reading in between
        p.move(rng.uniform(200, 1200), rng.uniform(800, 880), rng.uniform(400, 700), curve=0.05)
        p.rest(rng.uniform(2000, 5000) * calm_factor)
        start = p.t
        for _ in range(rng.randint(3, 6)):                 # back-and-forth between two phones
            for c in (a, b):
                x, y = p.card_point(c, rng.choice(["battery", "camera", "chip", "price"]))
                p.move(x, y, rng.uniform(220, 380), curve=rng.uniform(0.15, 0.35), jitter=2.0)
                p.rest(rng.uniform(250, 500))
        x, y = p.card_point(a, "battery")                  # freeze on a spec
        p.move(x, y, 250, curve=0.2)
        p.rest(rng.uniform(1500, 2800))
        if rng.random() < 0.6:                             # pause in empty space
            p.move(card_box(a)[1] + 8, rng.uniform(400, 700), 250, curve=0.2)
            p.rest(rng.uniform(1200, 2500))
        if rng.random() < 0.5:
            for d in (120, -120, 120, -120):
                p.scroll_by(d)
        episodes.append([start, p.t])
        p.rest(rng.uniform(800, 2000))
    buy = rng.randrange(4)
    x0, x1 = card_box(buy)
    p.move((x0 + x1) / 2, 735, rng.uniform(400, 700), curve=0.05)
    p.rest(400)
    return p, episodes, p.t, buy


def walk(client, study, rng, cond_effects=None, verbose=True):
    r = client.post("/api/participants", json={"study": study}).json()
    token = r["token"]
    with db.engine.begin() as c:
        c.execute(db.participants.update().where(db.participants.c.token == token).values(simulated=True))
    me = client.get(f"/api/me?token={token}").json()
    hesitant_person = rng.random() < 0.8
    episodes_by_task = {}

    def step_submit(st, data=None, task_key=None):
        nonlocal me
        body = {"token": token, "step_index": me["step_index"], "step_key": st["key"], "kind": st["kind"],
                "data": data or {}, "task_key": task_key}
        me = client.post("/api/step", json=body).json()

    while me["step_index"] < len(me["plan"]) - 1:
        st = me["plan"][me["step_index"]]
        kind = st["kind"]
        if kind == "consent":
            step_submit(st, {"agree": True})
        elif kind == "device_check":
            step_submit(st, {"viewport_w": VIEW_W, "viewport_h": VIEW_H, "dpr": 1, "pointer_types": ["mouse"], "simulated": True})
        elif kind == "task":
            t = client.post("/api/task/start", json={"token": token, "task_key": st["task_key"],
                                                      "viewport": {"w": VIEW_W, "h": VIEW_H, "dpr": 1}}).json()
            order = t["card_order"]
            cond = t["condition"]
            base = st["task_kind"].startswith("baseline") or st["task_kind"] == "practice"
            calm = 0.7 if base else 1.0
            path, eps, t_end, buy_i = make_task(order, rng, hesitant=(not base and hesitant_person),
                                                n_episodes=0 if base else None, calm_factor=calm)
            if cond == "C3":     # the smart condition shortens decisions in this simulation
                t_end = int(t_end * 0.85)
            episodes_by_task[st["task_key"]] = eps
            seq, now, mi, si = 0, 500, 0, 0
            while now <= t_end:
                mb, sb = [], []
                while mi < len(path.m) and path.m[mi][0] <= now:
                    mb.append(path.m[mi]); mi += 1
                while si < len(path.s) and path.s[si][0] <= now:
                    sb.append(path.s[si]); si += 1
                resp = client.post(f"/api/task/{t['task_id']}/events",
                                   json={"token": token, "seq": seq, "now": now, "m": mb, "s": sb, "c": []}).json()
                seq += 1
                if resp.get("popup"):
                    pop = resp["popup"]
                    in_ep = any(a - 1000 <= now <= b + 2000 for a, b in eps)
                    yes = rng.random() < (0.85 if in_ep else 0.25)
                    client.post(f"/api/popup/{pop['id']}/unsure", json={"token": token, "t": now, "answer": "yes" if yes else "no"})
                    accept = rng.random() < (0.65 if yes else 0.2)
                    choice = (pop["predicted_type"] if rng.random() < 0.7 else rng.choice(["compare", "explain", "general"])) if accept else "dismiss"
                    client.post(f"/api/popup/{pop['id']}/choice", json={"token": token, "t": now + 1500, "choice": choice})
                    if choice != "dismiss":
                        client.post(f"/api/popup/{pop['id']}/closed", json={"token": token, "t": now + 15000})
                now += 500
            if cond == "C2" and rng.random() < 0.6:
                client.post(f"/api/task/{t['task_id']}/ask", json={"token": token, "t": t_end // 2, "mode": "compare", "pair": order[:2]})
            # choice: correctness depends on the condition (simulation only)
            phones = [ph["id"] for ph in t["set"]["phones"]]
            p_correct = (cond_effects or {}).get(cond, 0.5)
            if st["set"] == "P":
                answers = {"baseline1": "P4", "baseline2": "P2", "practice": "P3"}
                chosen = answers[st["task_kind"]]
            else:
                ranked = sorted(phones)                 # ids end with A (correct), B, C, D
                chosen = ranked[0] if rng.random() < p_correct else rng.choice(ranked[1:])
            client.post(f"/api/task/{t['task_id']}/end", json={"token": token, "chosen": chosen, "decision_ms": int(t_end)})
            step_submit(st, {}, st["task_key"])
        elif kind == "switch":
            info = client.get(f"/api/task/by-key/{st['task_key']}?token={token}").json()
            fin = info["chosen"]
            if not fin.endswith("A") and rng.random() < 0.2:
                fin = fin[:-1] + "A"
            client.post(f"/api/task/{info['task_id']}/switch", json={"token": token, "final_choice": fin})
            step_submit(st, {"final_choice": fin}, st["task_key"])
        elif kind == "confidence":
            step_submit(st, {"confidence": rng.randint(3, 7)}, st["task_key"])
        elif kind == "post_task":
            d = {"confidence": rng.randint(3, 7), "valence": rng.randint(3, 8), "arousal": rng.randint(2, 7),
                 **{k: rng.randrange(10, 90, 5) for k in analysis.TLX_KEYS}}
            if st["condition"] != "C1":
                d.update({k: rng.randint(2, 7) for k in ("helpful", "timing", "intrusive", "trust1", "trust2", "trust3", "trust4")})
                if st["condition"] == "C3":
                    d["timing"] = min(7, d["timing"] + 1)
            d["condition"] = st["condition"]
            step_submit(st, d, st["task_key"])
        elif kind == "replay":
            info = client.get(f"/api/task/by-key/{st['task_key']}?token={token}").json()
            eps = episodes_by_task.get(st["task_key"], [])
            labs = []
            for a, b in eps:
                if rng.random() < 0.9:
                    lag = rng.uniform(300, 1800)
                    labs.append([int(a + lag), int(b + lag * 0.5)])
            client.post(f"/api/task/{info['task_id']}/labels", json={"token": token, "intervals": labs})
            step_submit(st, {"n_marked": len(labs)}, st["task_key"])
        elif kind == "sus":
            step_submit(st, {**{f"q{i}": rng.randint(2, 5) if i % 2 else rng.randint(1, 3) for i in range(1, 11)},
                             "condition": st["condition"], "round": st["round"]})
        elif kind == "ranking":
            conds = [r["condition"] for r in st["rounds"]]
            pref = sorted(conds, key=lambda c: {"C3": 0, "C2": 1, "C4": 2, "C1": 3}[c] + rng.uniform(-1.2, 1.2))
            step_submit(st, {"ranks": {c: i + 1 for i, c in enumerate(pref)}})
        elif kind == "interview":
            step_submit(st, {"q1": "simulated", "q2": "", "q3": ""})
        else:
            step_submit(st, {"keep": True} if kind == "debrief" else {})
    if verbose:
        print(f"  {me['code']} done ({study})")
    return me["code"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=int, default=0)
    ap.add_argument("--main", type=int, default=0)
    ap.add_argument("--freeze", action="store_true", help="run the pilot analysis (incl. simulated) and freeze")
    ap.add_argument("--ai-check", type=int, default=0, help="how many of the pilot participants get the AI check round")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    client = TestClient(appmain.app)
    print(f"Database: {db.engine.url.render_as_string(hide_password=True)}")
    for i in range(a.pilot):
        db.set_setting("pilot_ai_check_next", i >= a.pilot - a.ai_check)
        walk(client, "pilot", rng)
    db.set_setting("pilot_ai_check_next", False)
    if a.freeze:
        res = analysis.pilot_analysis(include_sim=True)
        prop = res.get("proposal") or {}
        print("Pilot analysis:", {"people": res.get("n_people"), "tasks": res.get("n_tasks"), "chosen": res.get("chosen"),
                                  "loo_avg_precision": (res.get("loo") or {}).get("avg", {}).get("precision_mean")})
        db.set_setting("pilot_analysis_last", {"proposal": prop, "n_people": res.get("n_people"), "n_tasks": res.get("n_tasks"),
                                               "include_simulated": True, "chosen": res.get("chosen")})
        thr = prop.get("threshold") or 1.5
        r = client.post("/api/admin/login", json={"password": os.environ.get("ADMIN_PASSWORD", "") or appmain.config.ADMIN_PASSWORD})
        if r.status_code != 200:
            print("Login failed; set ADMIN_PASSWORD in .env"); return
        fr = client.post("/api/admin/freeze", json={"threshold": thr, "note": "" if prop.get("threshold") else "simulation: no threshold passed; using 1.5"})
        print("Freeze:", fr.status_code, fr.json().get("threshold", fr.json()))
    effects = {"C1": 0.5, "C2": 0.58, "C3": 0.66, "C4": 0.55}
    for _ in range(a.main):
        walk(client, "main", rng, cond_effects=effects)


if __name__ == "__main__":
    main()
