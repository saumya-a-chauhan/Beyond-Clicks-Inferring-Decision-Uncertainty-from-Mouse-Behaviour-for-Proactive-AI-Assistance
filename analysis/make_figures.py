"""Offline analysis: all report figures + mixed-effects statistics.

Reads straight from the study database (the same DATABASE_URL the website uses), so set
DATABASE_URL to the cloud database to analyse the real data, or leave it empty for the local file.

    .venv/Scripts/python analysis/make_figures.py --study pilot
    .venv/Scripts/python analysis/make_figures.py --study main
    (add --include-simulated to test on fake data)

Output: analysis/figures/*.png and analysis/figures/stats_<study>.txt
Figure numbers follow the protocol's list of 22 plots.
"""
import argparse
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import analysis, db  # noqa: E402
from app.detector import compute_ticks, simulate  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
COND = {"C1": "No AI", "C2": "Ask AI", "C3": "Smart pop-up", "C4": "Random pop-up"}
COLORS = {"C1": "#8a93a6", "C2": "#e07b28", "C3": "#3557d6", "C4": "#b9bfcc"}
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name))
    plt.close(fig)
    print("  wrote", name)


def load(study, include_sim):
    with db.engine.connect() as c:
        ps = [dict(r._mapping) for r in c.execute(select(db.participants).where(db.participants.c.study == study))]
        ps = [p for p in ps if not p["excluded"] and (include_sim or not p["simulated"])]
        ids = [p["id"] for p in ps]
        tasks = [dict(r._mapping) for r in c.execute(select(db.tasks).where(db.tasks.c.participant_id.in_(ids)))] if ids else []
        tids = [t["id"] for t in tasks]
        pops = [dict(r._mapping) for r in c.execute(select(db.popups).where(db.popups.c.task_id.in_(tids)))] if tids else []
        labels = {r.task_id: db.loads(r.intervals, []) for r in c.execute(select(db.labels).where(db.labels.c.task_id.in_(tids)))} if tids else {}
        resp = [dict(r._mapping) for r in c.execute(select(db.responses).where(db.responses.c.participant_id.in_(ids)))] if ids else []
        events = {t["id"]: db.task_events(c, t["id"]) for t in tasks if t["kind"] in ("main", "pilot_ai")}
    code = {p["id"]: p["code"] for p in ps}
    for t in tasks:
        t["code"] = code[t["participant_id"]]
    return ps, tasks, pops, labels, resp, events


# ------------------------------------------------------------------ helpers
def final_move_curvature(ev):
    """Maximum deviation (px) and area (px^2/1000) of the last movement before the Buy click,
    relative to the straight line (mouse-tracking measures MD and AUC)."""
    m = ev["m"]
    clicks = [c for c in ev["c"] if (c[4] if len(c) > 4 else "").startswith("buy:")]
    if not m or not clicks:
        return None, None
    t_click = clicks[-1][0]
    pts = [e for e in m if e[0] <= t_click]
    if len(pts) < 3:
        return None, None
    start = len(pts) - 1           # walk back to the last rest (gap > 150 ms)
    while start > 0 and pts[start][0] - pts[start - 1][0] < 150:
        start -= 1
    seg = pts[start:]
    if len(seg) < 3:
        return None, None
    (x0, y0), (x1, y1) = seg[0][1:3], seg[-1][1:3]
    L = math.hypot(x1 - x0, y1 - y0)
    if L < 30:
        return None, None
    dev = [((x1 - x0) * (y0 - p[2]) - (x0 - p[1]) * (y1 - y0)) / L for p in seg]
    md = max(abs(d) for d in dev)
    proj = [((p[1] - x0) * (x1 - x0) + (p[2] - y0) * (y1 - y0)) / L for p in seg]
    area = abs(np.trapezoid(dev, proj)) / 1000.0
    return md, area


def roc_points(pos, neg):
    th = sorted(set(pos + neg), reverse=True)
    pts = [(0.0, 0.0)]
    for t in th:
        tpr = sum(p >= t for p in pos) / len(pos)
        fpr = sum(n >= t for n in neg) / len(neg)
        pts.append((fpr, tpr))
    pts.append((1.0, 1.0))
    return pts


# ------------------------------------------------------------------ pilot
def pilot(include_sim):
    res = analysis.pilot_analysis(include_sim=include_sim)
    if not res.get("sweeps"):
        print(res.get("message"))
        return
    ps, tasks, pops, labels, resp, events = load("pilot", include_sim)
    cfg = dict(res["settings_used"])
    lines = [f"Pilot analysis: {res['n_people']} people, {res['n_tasks']} tasks",
             f"Chosen thresholds: {res['chosen']}", f"Chance precision: {res['chance_precision']}",
             f"Minimum spreads: {res['min_spread']}  (share below: {res['floor_use']})",
             f"Random pop-up rate: {res['c4_rate_per_min']} per min", ""]
    for v in ("avg", "max", "B", "I"):
        lo = res["loo"][v]
        lines.append(f"LOO {v}: precision {lo['precision_mean']} +- {lo['precision_sd']}, recall {lo['recall_mean']} +- {lo['recall_sd']}")

    # Fig 1: confident vs hesitant trajectory
    main_t = [t for t in tasks if t["kind"] == "main" and t["id"] in events and t["id"] in labels]
    if main_t:
        by_lab = sorted(main_t, key=lambda t: sum(b - a for a, b in labels[t["id"]]))
        fig, ax = plt.subplots(1, 2, figsize=(10, 4), sharex=True, sharey=True)
        for a, t, title in ((ax[0], by_lab[0], "Least time marked unsure"), (ax[1], by_lab[-1], "Most time marked unsure")):
            m = np.array([[e[1], e[2]] for e in events[t["id"]]["m"]])
            if len(m):
                a.plot(m[:, 0], m[:, 1], lw=.6, color="#3557d6")
            a.invert_yaxis(); a.set_title(f"{title} ({t['code']} {t['task_key']})"); a.set_xlabel("x (px)")
        ax[0].set_ylabel("y (px)")
        save(fig, "01_trajectories.png")

        # Fig 2: heatmap of cursor positions
        xy = np.array([[e[1], e[2]] for t in main_t for e in events[t["id"]]["m"]])
        if len(xy):
            fig, ax = plt.subplots(figsize=(8, 4.5))
            hb = ax.hexbin(xy[:, 0], xy[:, 1], gridsize=45, cmap="Blues", mincnt=1, bins="log")
            ax.invert_yaxis(); ax.set_title("Where cursors spend time (pilot shopping tasks)")
            fig.colorbar(hb, ax=ax, label="samples (log)")
            save(fig, "02_heatmap.png")

        # Fig 3: one person's full timeline with labels and simulated triggers
        t = by_lab[-1]
        p = next(x for x in ps if x["id"] == t["participant_id"])
        with db.engine.connect() as c:
            base = analysis.person_baseline(c, {k["task_key"]: k for k in tasks if k["participant_id"] == p["id"]}, cfg)
        ev = events[t["id"]]
        ticks = compute_ticks(ev["m"], ev["s"], db.loads(t["card_order"], []), base, cfg, int(t["decision_ms"]))
        thr = res["chosen"]["avg"] or cfg["threshold"]
        fires = simulate(ticks, cfg, "avg", thr)
        ts = np.array([k["t"] for k in ticks]) / 1000
        fig, ax = plt.subplots(2, 1, figsize=(10, 5), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
        for s, col in zip("BFIWS", ["#3557d6", "#e07b28", "#3d8b5f", "#7b4fc4", "#c0392b"]):
            ax[1].plot(ts, [k["z"][s] for k in ticks], lw=.8, color=col, label=f"z {s}")
        ax[0].plot(ts, [k["scores"]["avg"] for k in ticks], color="#111", lw=1.2, label="Hesitation score")
        ax[0].axhline(thr, ls="--", color="#999", label=f"Threshold {thr}")
        for a, b in labels[t["id"]]:
            for axx in ax:
                axx.axvspan(a / 1000, b / 1000, color="#ff6b6b", alpha=.18, lw=0)
        for f in fires:
            ax[0].axvline(f / 1000, color="#3557d6", lw=1.5)
        ax[0].set_title(f"{t['code']} {t['task_key']}: score, marked 'unsure' moments (red) and pop-ups (blue)")
        ax[0].legend(loc="upper left", fontsize=8); ax[1].legend(ncol=5, fontsize=7); ax[1].set_xlabel("Time (s)")
        save(fig, "03_timeline.png")

    # Fig 4: precision / recall vs threshold
    sw = res["sweeps"]["avg"]
    fig, ax = plt.subplots(figsize=(7, 4))
    thr_x = [r["threshold"] for r in sw]
    ax.plot(thr_x, [100 * (r["precision"] or 0) for r in sw], "o-", color="#3557d6", label="Precision")
    ax.plot(thr_x, [100 * (r["recall"] or 0) for r in sw], "o-", color="#e07b28", label="Recall")
    ax.axhline(70, ls="--", color="#999", label="70% precision rule")
    if res["chance_precision"] is not None:
        ax.axhline(100 * res["chance_precision"], ls=":", color="#c0392b", label="Chance")
    if res["chosen"]["avg"] is not None:
        ax.axvline(res["chosen"]["avg"], color="#111", lw=1, label=f"Chosen {res['chosen']['avg']}")
    ax.set_ylim(0, 100); ax.set_xlabel("Threshold"); ax.set_ylabel("%"); ax.legend(fontsize=8)
    ax.set_title("Main detector: precision and recall by threshold (pilot)")
    save(fig, "04_precision_recall.png")

    # Fig 5: leave-one-out per person
    rows = res["loo"]["avg"]["rows"]
    fig, ax = plt.subplots(figsize=(8, 3.5))
    xs = np.arange(len(rows))
    ax.bar(xs - .2, [100 * (r["precision"] or 0) for r in rows], .4, label="Precision", color="#3557d6")
    ax.bar(xs + .2, [100 * (r["recall"] or 0) for r in rows], .4, label="Recall", color="#e07b28")
    ax.set_xticks(xs, [r["person"] for r in rows]); ax.set_ylim(0, 100); ax.legend(); ax.set_ylabel("%")
    ax.set_title("Leave-one-person-out: detector on people it has never seen")
    save(fig, "05_leave_one_out.png")

    # Fig 7: phone-set difficulty
    sets = res["sets"]
    fig, ax = plt.subplots(figsize=(5, 3.5))
    ax.bar([s["set"] for s in sets], [100 * s["correct_rate"] for s in sets], color="#7a9cff")
    ax.axhspan(40, 60, color="#3d8b5f", alpha=.12, label="target 40-60%")
    ax.set_ylim(0, 100); ax.set_ylabel("% correct (no AI)"); ax.legend(); ax.set_title("Phone sets are equally hard")
    save(fig, "07_set_difficulty.png")

    with open(os.path.join(OUT, "stats_pilot.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(str(x) for x in lines))
    print("\n".join(lines))


# ------------------------------------------------------------------ main
def main_study(include_sim):
    res = analysis.main_results(include_sim=include_sim)
    if not res.get("conditions"):
        print(res.get("message"))
        return
    ps, tasks, pops, labels, resp, events = load("main", include_sim)
    mt = pd.DataFrame([t for t in tasks if t["kind"] == "main" and t["decision_ms"]])
    mt["time_s"] = mt["decision_ms"] / 1000
    mt["log_time"] = np.log(mt["time_s"])
    mt["correct_i"] = mt["correct"].astype(int)
    order = ["C1", "C2", "C3", "C4"]

    # Fig 8: yes rate C3 vs C4
    pr = res["popups"]
    fig, ax = plt.subplots(figsize=(5, 3.8))
    vals = [pr[c]["yes_rate"] or 0 for c in ("C3", "C4")]
    err = [[100 * (v - (pr[c]["yes_lo"] or 0)) for v, c in zip(vals, ("C3", "C4"))],
           [100 * ((pr[c]["yes_hi"] or 0) - v) for v, c in zip(vals, ("C3", "C4"))]]
    ax.bar([COND["C3"], COND["C4"]], [100 * v for v in vals], yerr=err, capsize=6, color=[COLORS["C3"], COLORS["C4"]])
    ax.set_ylim(0, 100); ax.set_ylabel("% 'Yes, I was unsure just now'"); ax.set_title("Pop-ups from the detector vs at random times")
    save(fig, "08_unsure_yes_rate.png")

    # Fig 9: decision time violins
    fig, ax = plt.subplots(figsize=(7, 4))
    data = [mt[mt.condition == c]["time_s"].values for c in order]
    parts = ax.violinplot([d if len(d) else [0] for d in data], showmedians=True)
    for b, c in zip(parts["bodies"], order):
        b.set_facecolor(COLORS[c]); b.set_alpha(.6)
    ax.set_xticks(range(1, 5), [COND[c] for c in order]); ax.set_ylabel("Decision time (s)"); ax.set_ylim(bottom=0)
    ax.set_title("Decision time per condition (line = median)")
    save(fig, "09_decision_time.png")

    # Fig 10 + 11: correctness with CI, switch and dominated rates
    cr = {r["condition"]: r for r in res["conditions"]}
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    v = [100 * (cr[c]["correct"] or 0) for c in order]
    e = [[v[i] - 100 * (cr[c]["correct_lo"] or 0) for i, c in enumerate(order)], [100 * (cr[c]["correct_hi"] or 0) - v[i] for i, c in enumerate(order)]]
    ax[0].bar([COND[c] for c in order], v, yerr=e, capsize=5, color=[COLORS[c] for c in order])
    ax[0].set_ylim(0, 100); ax[0].set_ylabel("% chose the correct phone"); ax[0].set_title("Correctness (95% CI)")
    x = np.arange(4)
    ax[1].bar(x - .2, [100 * (cr[c]["switch_rate"] or 0) for c in order], .4, label="Switched after full table", color="#7a9cff")
    ax[1].bar(x + .2, [100 * (cr[c]["dominated_rate"] or 0) for c in order], .4, label="Chose dominated phone", color="#c0392b")
    ax[1].set_xticks(x, [COND[c] for c in order]); ax[1].set_ylim(0, 100); ax[1].legend(fontsize=8); ax[1].set_title("Decision quality, two more ways")
    save(fig, "10_11_quality.png")

    # Fig 12: speed vs quality
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    for c in order:
        ax.scatter(cr[c]["median_time_s"] or 0, cr[c]["mean_rank"] or 0, s=140, color=COLORS[c], label=COND[c], edgecolor="#222")
    ax.set_xlabel("Median decision time (s)  <- faster"); ax.set_ylabel("Mean rank of chosen phone  <- better"); ax.invert_yaxis()
    ax.legend(fontsize=8); ax.set_title("Speed vs decision quality (goal: top-left)")
    save(fig, "12_speed_vs_quality.png")

    # Fig 13: paired lines C1 vs C3
    wide = mt.pivot_table(index="code", columns="condition", values="time_s")
    if {"C1", "C3"} <= set(wide.columns):
        fig, ax = plt.subplots(figsize=(4.5, 4.2))
        for _, r in wide[["C1", "C3"]].dropna().iterrows():
            ax.plot([0, 1], [r["C1"], r["C3"]], "-o", color="#3557d6" if r["C3"] < r["C1"] else "#c0392b", alpha=.6)
        ax.set_xticks([0, 1], [COND["C1"], COND["C3"]]); ax.set_ylabel("Decision time (s)")
        ax.set_title("Each person: No AI vs Smart pop-up\n(blue = faster with pop-up)")
        save(fig, "13_paired_time.png")

    # Fig 14: score aligned to pop-up
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for g, col in (("C3", COLORS["C3"]), ("C4", "#777")):
        pts = res["aligned"].get(g) or []
        if pts:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, label=COND[g])
    ax.axvline(0, color="#111", lw=.8); ax.set_xlabel("Seconds from pop-up"); ax.set_ylabel("Mean hesitation score")
    ax.legend(); ax.set_title("Hesitation score around the pop-up (event-aligned, like an ERP)")
    save(fig, "14_score_around_popup.png")

    # Fig 15: acceptance by type
    pp = pd.DataFrame(pops)
    if len(pp):
        fig, ax = plt.subplots(figsize=(6, 3.8))
        tab = pp.assign(choice=pp["choice"].fillna("no answer")).groupby(["source", "choice"]).size().unstack(fill_value=0)
        tab.plot(kind="bar", stacked=True, ax=ax, colormap="tab20c")
        ax.set_xticklabels([{"detector": "Smart pop-up", "random": "Random pop-up"}.get(t.get_text(), t.get_text()) for t in ax.get_xticklabels()], rotation=0)
        ax.set_ylabel("Pop-ups"); ax.set_title("What people did with the pop-up"); ax.legend(fontsize=8)
        save(fig, "15_popup_choices.png")

    # Fig 16: curvature of the final move to Buy
    mt["md"], mt["auc_px"] = zip(*[final_move_curvature(events.get(i, {"m": [], "c": []})) for i in mt["id"]])
    fig, ax = plt.subplots(figsize=(6, 3.8))
    ax.boxplot([mt[(mt.condition == c) & mt.md.notna()]["md"].values for c in order], tick_labels=[COND[c] for c in order])
    ax.set_ylabel("Maximum deviation of final move (px)"); ax.set_title("Inner conflict at the moment of buying")
    save(fig, "16_final_move_curvature.png")

    # Fig 17-19: questionnaires
    q = res["questionnaires"]
    keys = ["tlx", "confidence", "valence", "arousal"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    x = np.arange(len(keys))
    for i, c in enumerate(order):
        ax[0].bar(x + (i - 1.5) * .2, [(q.get(c) or {}).get(k, 0) for k in keys], .2, color=COLORS[c], label=COND[c])
    ax[0].set_xticks(x, ["Workload (TLX 0-100)", "Confidence (1-7)", "Valence (1-9)", "Arousal (1-9)"]); ax[0].legend(fontsize=7)
    ax[0].set_yscale("symlog"); ax[0].set_title("Workload and feelings")
    k2 = ["helpful", "timing", "intrusive", "trust"]
    x = np.arange(len(k2))
    for i, c in enumerate(["C2", "C3", "C4"]):
        ax[1].bar(x + (i - 1) * .25, [(q.get(c) or {}).get(k, 0) for k in k2], .25, color=COLORS[c], label=COND[c])
    ax[1].set_xticks(x, ["Useful", "Well timed", "Intrusive", "Trust"]); ax[1].set_ylim(1, 7); ax[1].legend(fontsize=7)
    ax[1].set_title("Ratings of the AI help (1-7)")
    save(fig, "17_18_questionnaires.png")

    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    sus = res["sus"]
    ax[0].bar([COND[c] for c in ("C2", "C3", "C4")], [(sus.get(c) or {}).get("mean", 0) for c in ("C2", "C3", "C4")], color=[COLORS[c] for c in ("C2", "C3", "C4")])
    ax[0].axhline(68, ls="--", color="#999", label="SUS average (68)"); ax[0].set_ylim(0, 100); ax[0].legend(); ax[0].set_title("Usability (SUS)")
    pref = res["preference_rank"]
    ax[1].bar([COND[c] for c in order], [pref.get(c, 0) for c in order], color=[COLORS[c] for c in order])
    ax[1].invert_yaxis(); ax[1].set_ylabel("Mean preference rank (1 = best)"); ax[1].set_title("Which round people preferred")
    save(fig, "19_20_sus_preference.png")

    # Fig 21: order check
    oc = res["order_check"]
    fig, ax = plt.subplots(figsize=(5.5, 3.5))
    ax.plot([o["position"] for o in oc], [o["median_time_s"] for o in oc], "o-", color="#3557d6")
    ax.set_xlabel("Round position"); ax.set_ylabel("Median time (s)"); ax.set_title("Order check: learning or tiredness?")
    save(fig, "21_order_check.png")

    # Fig 22: ROC of the 4 detectors at random C4 moments
    ticks = {t["id"]: db.unpack(t["ticks"], []) for t in tasks}
    c4 = [p for p in pops if p["source"] == "random" and p["unsure_answer"] in ("yes", "no")]
    fig, ax = plt.subplots(figsize=(4.8, 4.5))
    for v, col in zip(("avg", "max", "B", "I"), ("#3557d6", "#e07b28", "#3d8b5f", "#7b4fc4")):
        pos, neg = [], []
        for p in c4:
            tk = analysis._tick_at(ticks.get(p["task_id"], []), p["t_ms"])
            if tk:
                (pos if p["unsure_answer"] == "yes" else neg).append(tk["scores"][v])
        if pos and neg:
            pts = roc_points(pos, neg)
            ax.plot([a for a, b in pts], [b for a, b in pts], color=col, label=f"{v} (AUC {analysis.auc(pos, neg):.2f})")
    ax.plot([0, 1], [0, 1], ls=":", color="#999")
    ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate"); ax.legend(fontsize=8)
    ax.set_title("Detectors at random moments (C4)")
    save(fig, "22_roc_random_moments.png")

    # ---------------- statistics
    lines = [f"Main study: {res['n_people']} people, {res['n_tasks_done']} rounds", ""]
    try:
        import statsmodels.formula.api as smf
        mt["condition"] = pd.Categorical(mt["condition"], categories=order)
        m1 = smf.mixedlm("log_time ~ C(condition) + C(set_id) + position", mt, groups=mt["code"]).fit(reml=True)
        lines += ["== log(decision time): linear mixed model, random intercept per participant ==", str(m1.summary()),
                  "exp(coefficient) = time ratio vs No AI (e.g. 0.8 = 20% faster)", ""]
        m2 = smf.mixedlm("rank ~ C(condition) + C(set_id) + position", mt.dropna(subset=["rank"]), groups=mt.dropna(subset=["rank"])["code"]).fit(reml=True)
        lines += ["== rank of chosen phone (1 best): linear mixed model ==", str(m2.summary()), ""]
        import statsmodels.api as sm
        g = smf.gee("correct_i ~ C(condition) + C(set_id)", "code", mt, family=sm.families.Binomial(),
                    cov_struct=sm.cov_struct.Exchangeable()).fit()
        lines += ["== correct (yes/no): GEE logistic, exchangeable within participant ==", str(g.summary()),
                  "exp(coefficient) = odds ratio vs No AI", ""]
    except Exception as ex:  # noqa: BLE001 - small samples can fail to converge; report it
        lines.append(f"Model fitting problem: {type(ex).__name__}: {ex}")
    lines.append("Holm correction: apply to the family of condition contrasts you report (see docs/ANALYSIS.md).")
    with open(os.path.join(OUT, "stats_main.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  wrote stats_main.txt ({len(lines)} lines)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", choices=["pilot", "main"], required=True)
    ap.add_argument("--include-simulated", action="store_true")
    a = ap.parse_args()
    print("Database:", db.engine.url.render_as_string(hide_password=True))
    (pilot if a.study == "pilot" else main_study)(a.include_simulated)
