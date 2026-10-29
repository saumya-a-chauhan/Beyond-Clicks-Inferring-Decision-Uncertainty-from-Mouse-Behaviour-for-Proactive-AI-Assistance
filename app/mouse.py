"""Mouse-movement data for the results Excel: a summary per round, and the raw rows behind it.

The summary numbers are computed from the same logged events and detector ticks that the detector and the pilot
analysis use (app/features.py, app/detector.py), with the participant's own frozen settings.
"""
from math import hypot

from .features import card_of


def summary(ev, ticks, cfg, names):
    """Whole-round numbers for one task. ev = db.task_events(); names = {phone_id: phone name}."""
    m, s, c = ev["m"], ev["s"], ev["c"]
    rest_v = cfg["rest_speed_px_s"]
    path, moving_ms, resting_ms = 0.0, 0.0, 0.0
    hover = {}
    visits = []                     # [card, duration_ms] of consecutive time on one phone card
    longest = {"spec": 0.0, "empty": 0.0}
    run_zone, run_ms = None, 0.0
    for a, b in zip(m, m[1:]):
        dt = b[0] - a[0]
        if dt <= 0:
            continue
        d = hypot(b[1] - a[1], b[2] - a[2])
        path += d
        resting = d / (dt / 1000.0) < rest_v
        if resting:
            resting_ms += dt
        else:
            moving_ms += dt
        z = a[3] or "empty"
        kind = "spec" if z.startswith("spec:") else "empty" if z == "empty" else None
        if resting and kind:
            run_ms = run_ms + dt if z == run_zone else dt
            run_zone = z
            longest[kind] = max(longest[kind], run_ms)
        else:
            run_zone, run_ms = None, 0.0
        card = card_of(z)
        if card:
            hover[card] = hover.get(card, 0.0) + dt
            if visits and visits[-1][0] == card:
                visits[-1][1] += dt
            else:
                visits.append([card, dt])
    valid = [v for v in visits if v[1] >= cfg["visit_min_ms"]]
    switches = sum(1 for p, q in zip(valid, valid[1:]) if p[0] != q[0])
    flips, last = 0, 0
    for a, b in zip(s, s[1:]):
        d = b[1] - a[1]
        if d:
            sign = 1 if d > 0 else -1
            flips += 1 if last and sign != last else 0
            last = sign
    variant = cfg.get("variant", "avg")
    scores = [tk["scores"][variant] for tk in ticks]
    seen_t = next((tk["t"] for tk in ticks if tk["seen"]), None)
    thr = cfg["threshold"]
    return {
        "mouse_points": len(m),
        "mouse_path_px": round(path),
        "mouse_moving_s": round(moving_ms / 1000, 2),
        "mouse_resting_s": round(resting_ms / 1000, 2),
        "mouse_speed_px_s": round(path / (moving_ms / 1000)) if moving_ms else None,
        "clicks": len(c),
        "details_opened": sum(1 for e in c if len(e) > 4 and str(e[4]).startswith("details:")),
        "card_switches": switches,
        "longest_spec_rest_s": round(longest["spec"] / 1000, 2),
        "longest_empty_rest_s": round(longest["empty"] / 1000, 2),
        "scroll_events": len(s),
        "scroll_flips": flips,
        "hover_by_phone": "; ".join(f"{names.get(k, k)} {v / 1000:.1f} s" for k, v in
                                    sorted(hover.items(), key=lambda kv: -kv[1])) or None,
        "all_seen_s": round(seen_t / 1000, 1) if seen_t is not None else None,
        "score_peak": round(max(scores), 3) if scores else None,
        "score_mean": round(sum(scores) / len(scores), 3) if scores else None,
        "threshold_used": thr,
        "time_over_threshold_s": round(sum(1 for x in scores if x >= thr) * cfg["tick_ms"] / 1000, 1) if scores else None,
    }


SUMMARY_COLUMNS = [
    ("mouse_points", "Mouse positions logged in the round (about 60 per second while the mouse moves)"),
    ("mouse_path_px", "Total distance the cursor travelled, in pixels"),
    ("mouse_moving_s", "Seconds the cursor was moving (faster than the resting speed, 50 px/s)"),
    ("mouse_resting_s", "Seconds the cursor was resting (slower than 50 px/s)"),
    ("mouse_speed_px_s", "Average speed while moving, pixels per second"),
    ("clicks", "Clicks in the round"),
    ("details_opened", "Times 'View details' / 'Hide details' was clicked"),
    ("card_switches", "Moves from one phone card to another (visits of at least 200 ms) - sign B over the whole round"),
    ("longest_spec_rest_s", "Longest rest on one spec row, seconds - sign F"),
    ("longest_empty_rest_s", "Longest rest in empty space, seconds - sign I"),
    ("scroll_events", "Scroll events logged"),
    ("scroll_flips", "Times the scroll direction reversed - sign S"),
    ("hover_by_phone", "Seconds the cursor spent on each phone card, most first"),
    ("all_seen_s", "Seconds until every phone card had been hovered for 1 s (pop-ups can only come after this)"),
    ("score_peak", "Highest hesitation score in the round (the detector's 0.5 s checks)"),
    ("score_mean", "Mean hesitation score in the round"),
    ("threshold_used", "Hesitation threshold in this participant's settings"),
    ("time_over_threshold_s", "Seconds the hesitation score was at or above the threshold"),
]

TICK_HEAD = (["participant", "study", "round", "task_key", "condition", "phone_set", "t_s", "all_seen"]
             + [f"raw_{k}" for k in "BFIWS"] + [f"z_{k}" for k in "BFIWS"] + ["score", "over_threshold"])
EVENT_HEAD = ["participant", "study", "task_key", "task_kind", "round", "t_ms", "type", "x", "y", "scroll_y", "zone", "clicked"]


def tick_rows(base, ticks, cfg):
    variant, thr = cfg.get("variant", "avg"), cfg["threshold"]
    for tk in ticks:
        sc = tk["scores"][variant]
        yield (base + [round(tk["t"] / 1000, 2), bool(tk["seen"])]
               + [tk["raw"][k] if tk["raw"][k] is None else round(tk["raw"][k], 3) for k in "BFIWS"]
               + [round(tk["z"][k], 3) for k in "BFIWS"] + [round(sc, 3), sc >= thr])


def event_rows(base, ev):
    rows = ([(e[0], "move", e[1], e[2], None, e[3], None) for e in ev["m"]]
            + [(e[0], "scroll", None, None, e[1], e[2], None) for e in ev["s"]]
            + [(e[0], "click", e[1], e[2], None, e[3], e[4] if len(e) > 4 else None) for e in ev["c"]])
    rows.sort(key=lambda r: r[0])
    for r in rows:
        yield base + list(r)
