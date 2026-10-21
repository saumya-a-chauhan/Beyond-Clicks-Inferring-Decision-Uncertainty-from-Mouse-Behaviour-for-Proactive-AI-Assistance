"""Pilot analysis (threshold selection) and main-study results.

Pilot steps (protocol section 7):
  1. Per-person baseline from the two easy tasks.
  2. Minimum spreads = median baseline spread across pilot people (used before computing z).
  3. Score timeline for every pilot shopping task (same code as live).
  4. For every threshold, simulate pop-ups with the live trigger rules and score them against the
     replay labels (hit = within a labelled 'unsure' range, with a match margin).
  5. Pick the threshold with the pre-registered rule; check it with leave-one-person-out.
"""
import math
import statistics as st
from collections import defaultdict

from sqlalchemy import select

from . import db
from .defaults import DETECTOR_DEFAULTS, SELECTION_RULE, SIGNS, THRESHOLD_GRID
from .detector import compute_ticks, simulate
from .features import Timeline, baseline_stats

VARIANTS = ["avg", "max", "B", "I"]


def detector_cfg():
    saved = db.get_setting("detector", {}) or {}
    cfg = dict(DETECTOR_DEFAULTS)
    cfg.update({k: v for k, v in saved.items() if k != "min_spread"})
    cfg["min_spread"] = dict(DETECTOR_DEFAULTS["min_spread"], **(saved.get("min_spread") or {}))
    return cfg


# ---------------------------------------------------------------- loading
def _participants(conn, study, include_sim):
    q = select(db.participants).where(db.participants.c.study == study)
    rows = [dict(r._mapping) for r in conn.execute(q)]
    return [r for r in rows if not r["excluded"] and (include_sim or not r["simulated"])]


def _tasks(conn, pid):
    return {r.task_key: dict(r._mapping) for r in conn.execute(select(db.tasks).where(db.tasks.c.participant_id == pid))}


def _t_end(task, ev):
    if task.get("decision_ms"):
        return int(task["decision_ms"])
    times = [e[0] for e in ev["m"]] + [e[0] for e in ev["s"]]
    return int(max(times)) if times else 0


def person_baseline(conn, tasks, cfg):
    tls = []
    for k in ("baseline1", "baseline2"):
        t = tasks.get(k)
        if not t:
            continue
        ev = db.task_events(conn, t["id"])
        if ev["m"]:
            tls.append((Timeline(ev["m"], ev["s"]), _t_end(t, ev)))
    return baseline_stats(tls, cfg) if tls else None


# ---------------------------------------------------------------- scoring triggers vs labels
def score_triggers(triggers, intervals, margin):
    hits, caught = 0, 0
    exp = [(a - margin, b + margin) for a, b in intervals]
    for t in triggers:
        if any(a <= t <= b for a, b in exp):
            hits += 1
    for a, b in exp:
        if any(a <= t <= b for t in triggers):
            caught += 1
    return {"triggers": len(triggers), "hits": hits, "false_alarms": len(triggers) - hits,
            "labels": len(intervals), "caught": caught}


def summarise(counts, n_tasks):
    tr = sum(c["triggers"] for c in counts)
    hi = sum(c["hits"] for c in counts)
    la = sum(c["labels"] for c in counts)
    ca = sum(c["caught"] for c in counts)
    fa = sum(c["false_alarms"] for c in counts)
    return {"triggers": tr, "hits": hi, "labels": la, "caught": ca,
            "precision": (hi / tr) if tr else None, "recall": (ca / la) if la else None,
            "fa_per_task": (fa / n_tasks) if n_tasks else None}


def choose_threshold(rows, rule=SELECTION_RULE):
    """rows: list of {threshold, precision, recall, fa_per_task}. Pre-registered rule."""
    ok = [r for r in rows if r["precision"] is not None and r["recall"] is not None
          and r["precision"] >= rule["min_precision"] and r["fa_per_task"] <= rule["max_false_alarms_per_task"]]
    if not ok:
        return None
    best = max(r["recall"] for r in ok)
    near = [r for r in ok if r["recall"] >= best - 0.02]     # "almost equal" -> higher threshold
    return max(near, key=lambda r: r["threshold"])["threshold"]


def sweep(items, cfg, variant, grid=THRESHOLD_GRID, margin=None):
    margin = SELECTION_RULE["match_margin_ms"] if margin is None else margin
    out = []
    for thr in grid:
        counts = [score_triggers(simulate(it["ticks"], cfg, variant=variant, threshold=thr), it["labels"], margin)
                  for it in items]
        row = summarise(counts, len(items))
        row["threshold"] = thr
        out.append(row)
    return out


def _mean_sd(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None, None
    return st.mean(xs), (st.stdev(xs) if len(xs) > 1 else 0.0)


# ---------------------------------------------------------------- pilot
def pilot_analysis(include_sim=False):
    base_cfg = detector_cfg()
    with db.engine.connect() as conn:
        people = _participants(conn, "pilot", include_sim)
        persons = []
        for p in people:
            tasks = _tasks(conn, p["id"])
            base = person_baseline(conn, tasks, base_cfg)
            if base is None:
                continue
            items = []
            for k in ("t1", "t2", "t3", "t4"):
                t = tasks.get(k)
                if not t or not t["decision_ms"]:
                    continue
                lab = conn.execute(select(db.labels.c.intervals).where(db.labels.c.task_id == t["id"])).first()
                if lab is None:
                    continue
                ev = db.task_events(conn, t["id"])
                items.append({"task": t, "ev": ev, "labels": db.loads(lab[0], []), "t_end": _t_end(t, ev)})
            persons.append({"p": p, "tasks": tasks, "base": base, "items": items})
        ai_rows = _pilot_ai_check(conn, people)

    persons = [x for x in persons if x["items"]]
    res = {"n_people": len(persons), "n_tasks": sum(len(x["items"]) for x in persons),
           "rule": SELECTION_RULE, "grid": THRESHOLD_GRID, "settings_used": None}
    if not persons:
        res["message"] = "No pilot participants with baseline, finished tasks and replay labels yet."
        res["ai_check"] = ai_rows
        return res

    # 2. minimum spreads from pilot baselines: the median pilot spread, but never below the
    #    provisional design minimum (a near-zero median would make one sign explode).
    floors = {}
    for s in SIGNS:
        spreads = [x["base"][s]["spread"] for x in persons]
        med = st.median(spreads)
        floors[s] = round(max(med, DETECTOR_DEFAULTS["min_spread"][s]), 4)
    cfg = dict(base_cfg)
    cfg["min_spread"] = floors
    floor_use = {s: sum(1 for x in persons if x["base"][s]["spread"] < floors[s]) / len(persons) for s in SIGNS}

    # 3. ticks per task
    for x in persons:
        for it in x["items"]:
            it["ticks"] = compute_ticks(it["ev"]["m"], it["ev"]["s"], db.loads(it["task"]["card_order"], []),
                                        x["base"], cfg, it["t_end"])
    all_items = [it for x in persons for it in x["items"]]

    # 4. sweeps for main detector and comparison detectors
    sweeps = {v: sweep(all_items, cfg, v) for v in VARIANTS}
    chosen = {v: choose_threshold(sweeps[v]) for v in VARIANTS}

    # 5. leave-one-person-out
    loo = {}
    for v in VARIANTS:
        rows = []
        for i, x in enumerate(persons):
            train = [it for j, y in enumerate(persons) if j != i for it in y["items"]]
            thr = choose_threshold(sweep(train, cfg, v))
            if thr is None:
                rows.append({"person": x["p"]["code"], "threshold": None, "precision": None, "recall": None})
                continue
            counts = [score_triggers(simulate(it["ticks"], cfg, variant=v, threshold=thr), it["labels"],
                                     SELECTION_RULE["match_margin_ms"]) for it in x["items"]]
            s = summarise(counts, len(x["items"]))
            rows.append({"person": x["p"]["code"], "threshold": thr, "precision": s["precision"],
                         "recall": s["recall"], "fa_per_task": s["fa_per_task"]})
        pm, psd = _mean_sd([r["precision"] for r in rows])
        rm, rsd = _mean_sd([r["recall"] for r in rows])
        loo[v] = {"rows": rows, "precision_mean": pm, "precision_sd": psd, "recall_mean": rm, "recall_sd": rsd}

    # chance level: share of time (after all phones seen) marked unsure
    unsure_ms, total_ms = 0.0, 0.0
    durations, n_labels = [], []
    for it in all_items:
        seen_t = next((tk["t"] for tk in it["ticks"] if tk["seen"]), None)
        if seen_t is None:
            continue
        total_ms += max(0, it["t_end"] - seen_t)
        n_labels.append(len(it["labels"]))
        for a, b in it["labels"]:
            durations.append((b - a) / 1000.0)
            unsure_ms += max(0.0, min(b, it["t_end"]) - max(a, seen_t))
    chance = unsure_ms / total_ms if total_ms else None

    # pop-ups per minute at the chosen threshold -> rate for the random condition (C4)
    thr = chosen["avg"]
    c4_rate = None
    if thr is not None and total_ms:
        fires = sum(len(simulate(it["ticks"], cfg, "avg", thr)) for it in all_items)
        c4_rate = round(fires / (total_ms / 60000.0), 3)

    # label lag: cross-correlation between the main score and the 'unsure' indicator
    lags = list(range(-10, 11))   # in ticks of 0.5 s
    corr = []
    for L in lags:
        xs, ys = [], []
        for it in all_items:
            tks = it["ticks"]
            for k, tk in enumerate(tks):
                j = k + L
                if 0 <= j < len(tks):
                    tt = tks[j]["t"]
                    xs.append(tk["scores"]["avg"])
                    ys.append(1.0 if any(a <= tt <= b for a, b in it["labels"]) else 0.0)
        corr.append(_pearson(xs, ys))
    best_lag = None
    valid = [(c, L) for c, L in zip(corr, lags) if c is not None]
    if valid:
        best_lag = max(valid)[1] * cfg["tick_ms"] / 1000.0

    # phone-set difficulty (no AI) and decision times
    by_set = defaultdict(list)
    for x in persons:
        for k in ("t1", "t2", "t3", "t4"):
            t = x["tasks"].get(k)
            if t and t["correct"] is not None:
                by_set[t["set_id"]].append(t)
    set_rows = [{"set": s, "n": len(v), "correct_rate": sum(1 for t in v if t["correct"]) / len(v),
                 "median_time_s": st.median(t["decision_ms"] for t in v) / 1000.0} for s, v in sorted(by_set.items())]

    # cursor speed histogram (log10 px/s) to check the 50 px/s resting cut-off
    bins = [i / 4 for i in range(0, 17)]   # 1 .. 10^4 px/s
    hist = [0] * (len(bins) - 1)
    for it in all_items:
        tl = Timeline(it["ev"]["m"], it["ev"]["s"])
        for s0, e0, d, spd, z, xx, yy in tl.segments(0, it["t_end"]):
            if spd <= 0 or spd == float("inf"):
                continue
            lv = math.log10(max(1.0, spd))
            k = min(len(hist) - 1, int(lv * 4))
            hist[k] += 1

    res.update({
        "min_spread": floors, "floor_use": floor_use,
        "sweeps": sweeps, "chosen": chosen, "loo": loo,
        "chance_precision": chance,
        "c4_rate_per_min": c4_rate,
        "label_durations": {"median_s": st.median(durations) if durations else None, "n": len(durations)},
        "detection_delay_s": (cfg["window_ms"] + cfg["persistence_ticks"] * cfg["tick_ms"]) / 1000.0,
        "labels_per_task_mean": st.mean(n_labels) if n_labels else None,
        "label_lag": {"lags_s": [L * cfg["tick_ms"] / 1000.0 for L in lags], "corr": corr, "best_lag_s": best_lag},
        "sets": set_rows,
        "speed_hist": {"log10_edges": bins, "counts": hist, "rest_cutoff_log10": math.log10(cfg["rest_speed_px_s"])},
        "ai_check": ai_rows,
        "settings_used": {k: cfg[k] for k in cfg},
        "proposal": {"threshold": thr, "min_spread": floors, "c4_rate_per_min": c4_rate},
    })
    return res


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _pilot_ai_check(conn, people):
    ids = [p["id"] for p in people]
    if not ids:
        return {}
    trows = conn.execute(select(db.tasks.c.id).where(db.tasks.c.participant_id.in_(ids), db.tasks.c.task_key == "ai")).all()
    tids = [r[0] for r in trows]
    if not tids:
        return {"n_tasks": 0}
    pops = [dict(r._mapping) for r in conn.execute(select(db.popups).where(db.popups.c.task_id.in_(tids)))]
    reqs = [dict(r._mapping) for r in conn.execute(select(db.ai_requests).where(db.ai_requests.c.task_id.in_(tids)))]
    read_s = [(p["closed_ms"] - p["choice_ms"]) / 1000.0 for p in pops
              if p["closed_ms"] and p["choice_ms"] and p["choice"] != "dismiss"]
    return {
        "n_tasks": len(tids), "n_popups": len(pops),
        "unsure_yes": sum(1 for p in pops if p["unsure_answer"] == "yes"),
        "accepted": sum(1 for p in pops if p["choice"] in ("compare", "explain", "general")),
        "median_ai_latency_ms": st.median([r["latency_ms"] for r in reqs]) if reqs else None,
        "providers": dict(_count(r["provider"] for r in reqs)),
        "median_reading_s": st.median(read_s) if read_s else None,
    }


def _count(it):
    d = defaultdict(int)
    for x in it:
        d[x] += 1
    return d


# ---------------------------------------------------------------- main study
def wilson(k, n, z=1.96):
    if n == 0:
        return None, None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, max(0.0, c - h), min(1.0, c + h)


def auc(pos, neg):
    if not pos or not neg:
        return None
    wins = 0.0
    for a in pos:
        for b in neg:
            wins += 1.0 if a > b else 0.5 if a == b else 0.0
    return wins / (len(pos) * len(neg))


TLX_KEYS = ["mental", "physical", "temporal", "performance", "effort", "frustration"]


def sus_score(ans):
    try:
        vals = [int(ans[f"q{i}"]) for i in range(1, 11)]
    except (KeyError, TypeError, ValueError):
        return None
    tot = sum((v - 1) if i % 2 == 0 else (5 - v) for i, v in enumerate(vals))
    return tot * 2.5


def main_results(include_sim=False):
    with db.engine.connect() as conn:
        people = _participants(conn, "main", include_sim)
        ids = [p["id"] for p in people]
        codes = {p["id"]: p["code"] for p in people}
        if not ids:
            return {"n_people": 0, "message": "No main-study participants yet."}
        tasks = [dict(r._mapping) for r in conn.execute(
            select(db.tasks).where(db.tasks.c.participant_id.in_(ids), db.tasks.c.kind == "main"))]
        tids = [t["id"] for t in tasks]
        pops = [dict(r._mapping) for r in conn.execute(select(db.popups).where(db.popups.c.task_id.in_(tids)))] if tids else []
        reqs = [dict(r._mapping) for r in conn.execute(select(db.ai_requests).where(db.ai_requests.c.task_id.in_(tids)))] if tids else []
        resp = [dict(r._mapping) for r in conn.execute(select(db.responses).where(db.responses.c.participant_id.in_(ids)))]
        ticks = {t["id"]: db.unpack(t["ticks"], []) for t in tasks}

    done = [t for t in tasks if t["decision_ms"]]
    tmap = {t["id"]: t for t in tasks}
    by_cond = defaultdict(list)
    for t in done:
        by_cond[t["condition"]].append(t)

    cond_rows = []
    for c in ["C1", "C2", "C3", "C4"]:
        v = by_cond.get(c, [])
        n = len(v)
        k = sum(1 for t in v if t["correct"])
        p, lo, hi = wilson(k, n)
        times = sorted(t["decision_ms"] / 1000.0 for t in v)
        cond_rows.append({
            "condition": c, "n": n,
            "median_time_s": st.median(times) if times else None,
            "q1_time_s": times[len(times) // 4] if times else None,
            "q3_time_s": times[(3 * len(times)) // 4] if times else None,
            "correct": p, "correct_lo": lo, "correct_hi": hi,
            "mean_rank": st.mean(t["rank"] for t in v if t["rank"]) if v else None,
            "switch_rate": (sum(1 for t in v if t["switched"]) / n) if n else None,
            "dominated_rate": (sum(1 for t in v if t["rank"] == 4) / n) if n else None,
            "times": times,
        })

    # paired differences vs C1 (per person)
    per = defaultdict(dict)
    for t in done:
        per[t["participant_id"]][t["condition"]] = t
    paired = {}
    for c in ["C2", "C3", "C4"]:
        lr, dc, dr = [], [], []
        for pid, d in per.items():
            if "C1" in d and c in d:
                lr.append(math.log(d[c]["decision_ms"] / d["C1"]["decision_ms"]))
                dc.append(int(bool(d[c]["correct"])) - int(bool(d["C1"]["correct"])))
                if d[c]["rank"] and d["C1"]["rank"]:
                    dr.append(d[c]["rank"] - d["C1"]["rank"])
        paired[c] = {"n": len(lr),
                     "time_ratio_median": math.exp(st.median(lr)) if lr else None,
                     "correct_diff": _mean_ci(dc), "rank_diff": _mean_ci(dr)}

    # pop-ups: "were you unsure?" in C3 (detector) vs C4 (random)
    pop_rows = {}
    for src, c in (("detector", "C3"), ("random", "C4")):
        v = [p for p in pops if p["source"] == src]
        ans = [p for p in v if p["unsure_answer"] in ("yes", "no")]
        k = sum(1 for p in ans if p["unsure_answer"] == "yes")
        yes, lo, hi = wilson(k, len(ans))
        acc = [p for p in v if p["choice"] in ("compare", "explain", "general")]
        match = [p for p in acc if p["choice"] == p["predicted_type"]]
        pop_rows[c] = {"n_popups": len(v), "answered": len(ans), "yes_rate": yes, "yes_lo": lo, "yes_hi": hi,
                       "accept_rate": (len(acc) / len(v)) if v else None,
                       "type_match_rate": (len(match) / len(acc)) if acc else None,
                       "by_type": dict(_count(p["choice"] or "none" for p in v)),
                       "per_task": (len(v) / len(by_cond.get(c, []))) if by_cond.get(c) else None}

    # fair detector test at random (C4) moments
    auc_rows = {}
    c4 = [p for p in pops if p["source"] == "random" and p["unsure_answer"] in ("yes", "no")]
    for v in VARIANTS:
        pos, neg = [], []
        for p in c4:
            tk = _tick_at(ticks.get(p["task_id"], []), p["t_ms"])
            if tk is None:
                continue
            (pos if p["unsure_answer"] == "yes" else neg).append(tk["scores"][v])
        auc_rows[v] = {"auc": auc(pos, neg), "n_yes": len(pos), "n_no": len(neg)}

    # hesitation score 10 s before vs after the pop-up
    before_after = defaultdict(lambda: {"before": [], "after": []})
    for p in pops:
        tks = ticks.get(p["task_id"], [])
        if not tks:
            continue
        grp = ("C3" if p["source"] == "detector" else "C4") + (" accepted" if p["choice"] in ("compare", "explain", "general") else " dismissed")
        b = [tk["scores"]["avg"] for tk in tks if p["t_ms"] - 10000 <= tk["t"] < p["t_ms"]]
        a = [tk["scores"]["avg"] for tk in tks if (p["closed_ms"] or p["t_ms"]) < tk["t"] <= (p["closed_ms"] or p["t_ms"]) + 10000]
        if b and a:
            before_after[grp]["before"].append(st.mean(b))
            before_after[grp]["after"].append(st.mean(a))
    ba = {g: {"n": len(d["before"]), "before": st.mean(d["before"]), "after": st.mean(d["after"])}
          for g, d in before_after.items() if d["before"]}

    # event-aligned average score around the pop-up (-10 s .. +10 s)
    aligned = {}
    for grp in ("C3", "C4"):
        src = "detector" if grp == "C3" else "random"
        acc = defaultdict(list)
        for p in pops:
            if p["source"] != src:
                continue
            for tk in ticks.get(p["task_id"], []):
                off = tk["t"] - p["t_ms"]
                if -10000 <= off <= 10000:
                    acc[off // 500 * 0.5].append(tk["scores"]["avg"])
        aligned[grp] = sorted((k, st.mean(v)) for k, v in acc.items())

    # questionnaires
    q = defaultdict(lambda: defaultdict(list))
    sus = defaultdict(list)
    rank_scores = defaultdict(list)
    task_cond = {(t["participant_id"], t["task_key"]): t["condition"] for t in tasks}
    for r in resp:
        d = db.loads(r["data"], {}) or {}
        if r["kind"] == "post_task":
            c = task_cond.get((r["participant_id"], r["task_key"]))
            if not c:
                continue
            for key in ("confidence", "valence", "arousal", "helpful", "timing", "intrusive"):
                if d.get(key) not in (None, ""):
                    q[c][key].append(float(d[key]))
            tlx = [float(d[k]) for k in TLX_KEYS if d.get(k) not in (None, "")]
            if len(tlx) == 6:
                q[c]["tlx"].append(st.mean(tlx))
            tr = [float(d[k]) for k in ("trust1", "trust2", "trust3", "trust4") if d.get(k) not in (None, "")]
            if tr:
                q[c]["trust"].append(st.mean(tr))
        elif r["kind"] == "sus":
            s = sus_score(d)
            cond = d.get("condition")
            if s is not None and cond:
                sus[cond].append(s)
        elif r["kind"] == "ranking":
            for cond, rk in (d.get("ranks") or {}).items():
                rank_scores[cond].append(float(rk))
    quest = {c: {k: st.mean(v) for k, v in d.items() if v} for c, d in q.items()}

    by_pos = defaultdict(list)
    for t in done:
        by_pos[t["position"]].append(t)
    order_rows = [{"position": k, "n": len(v), "correct_rate": sum(1 for t in v if t["correct"]) / len(v),
                   "median_time_s": st.median(t["decision_ms"] for t in v) / 1000.0} for k, v in sorted(by_pos.items())]

    asks = [r for r in reqs if r["origin"] == "ask"]
    return {
        "n_people": len(people), "n_tasks_done": len(done),
        "conditions": cond_rows, "paired_vs_C1": paired, "popups": pop_rows, "auc_at_random_moments": auc_rows,
        "before_after": ba, "aligned": aligned, "questionnaires": quest,
        "sus": {c: {"mean": st.mean(v), "n": len(v)} for c, v in sus.items()},
        "preference_rank": {c: st.mean(v) for c, v in rank_scores.items()},
        "order_check": order_rows,
        "ask_ai": {"requests": len(asks), "tasks_with_use": len({r["task_id"] for r in asks}),
                   "c2_tasks": len(by_cond.get("C2", []))},
        "llm": {"providers": dict(_count(r["provider"] for r in reqs)),
                "median_latency_ms": st.median([r["latency_ms"] for r in reqs]) if reqs else None},
        "participants": [codes[i] for i in ids],
        "_task_count": len(tmap),
    }


def _tick_at(tks, t):
    best = None
    for tk in tks:
        if tk["t"] <= t:
            best = tk
        else:
            break
    return best


def _mean_ci(xs):
    if not xs:
        return None
    m = st.mean(xs)
    if len(xs) < 2:
        return {"mean": m, "lo": None, "hi": None, "n": len(xs)}
    se = st.stdev(xs) / math.sqrt(len(xs))
    return {"mean": m, "lo": m - 1.96 * se, "hi": m + 1.96 * se, "n": len(xs)}
