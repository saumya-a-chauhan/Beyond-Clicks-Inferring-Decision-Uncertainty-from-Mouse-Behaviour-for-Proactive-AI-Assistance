"""Unit tests for the hesitation detector, counterbalancing and the threshold rule."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///./_pytest.db")

from app.analysis import choose_threshold, score_triggers  # noqa: E402
from app.assign import _make_blocks  # noqa: E402
from app.defaults import COND_CODES, CYCLIC_ROWS, DETECTOR_DEFAULTS, MAIN_SETS, WILLIAMS_ROWS  # noqa: E402
from app.detector import TriggerRule, simulate  # noqa: E402
from app.features import SeenTracker, Timeline, detector_scores, features_at, predicted_type, robust_stats, zscores  # noqa: E402

CFG = dict(DETECTOR_DEFAULTS)


def moves(points, t0=0, dt=16):
    """Straight 16 ms samples through a list of (x, y, zone, n_samples)."""
    out, t = [], t0
    for x, y, z, n in points:
        for _ in range(n):
            t += dt
            out.append([t, x, y, z])
    return out, t


def test_back_and_forth_counts_switches_between_valid_visits():
    m, t = [], 0
    for k in range(6):                       # A, B, A, B, A, B with 300 ms each (valid visits)
        zone = "card:A" if k % 2 == 0 else "card:B"
        for _ in range(19):
            t += 16
            m.append([t, 100 + k, 200, zone])
    tl = Timeline(m, [])
    f = features_at(tl, t, CFG)
    assert f["B"] >= 4                         # 5 switches overall, most inside the 3 s window
    assert set(f["pair"]) == {"A", "B"}


def test_short_pass_over_a_card_is_not_a_visit():
    m = [[16, 10, 10, "card:A"], [400, 11, 10, "card:A"], [416, 300, 10, "card:C"],
         [500, 600, 10, "card:B"], [900, 601, 10, "card:B"]]   # C only 84 ms
    f = features_at(Timeline(m, []), 900, CFG)
    assert f["B"] == 1


def test_freezing_on_spec_row_and_pausing_in_empty_space():
    m = [[0, 50, 50, "spec:A:battery"], [2000, 51, 50, "spec:A:battery"],     # 2 s rest on a spec row
         [2016, 400, 400, "empty"], [3200, 401, 400, "empty"]]                # 1.2 s rest in empty space
    tl = Timeline(m, [])
    f = features_at(tl, 3200, CFG)
    assert 1.7 <= f["F"] <= 2.0
    assert f["spec"] == "battery"
    assert 1.1 <= f["I"] <= 1.25


def test_reading_zone_counts_as_neither_freezing_nor_pausing():
    m = [[0, 50, 50, "read:details"], [2500, 51, 50, "read:details"]]
    f = features_at(Timeline(m, []), 2600, CFG)
    assert f["F"] == 0 and f["I"] == 0


def test_wandering_ratio_straight_vs_curved():
    # rest, straight move of 300 px, rest
    straight = [[0, 0, 0, "empty"], [300, 0, 0, "empty"]] + [[300 + 16 * k, 20 * k, 0, "empty"] for k in range(1, 16)] + [[900, 300, 0, "empty"]]
    f = features_at(Timeline(straight, []), 1000, CFG)
    assert f["W"] is not None and abs(f["W"] - 1.0) < 0.05
    # curved: go up then come back down
    curved = [[0, 0, 0, "empty"], [300, 0, 0, "empty"]]
    pts = [(20 * k, 15 * k) for k in range(1, 8)] + [(140 + 20 * k, 105 - 15 * k) for k in range(1, 8)] + [(300, 0)]
    curved += [[300 + 16 * i, x, y, "empty"] for i, (x, y) in enumerate(pts, 1)]
    curved.append([900, 300, 0, "empty"])
    g = features_at(Timeline(curved, []), 1000, CFG)
    assert g["W"] > 1.15          # up 105 px and back over 300 px: path ~350 px -> ratio ~1.2


def test_wandering_ignores_tiny_moves():
    m = [[0, 0, 0, "empty"], [300, 0, 0, "empty"], [316, 5, 3, "empty"], [332, 8, 0, "empty"], [800, 8, 0, "empty"]]
    f = features_at(Timeline(m, []), 900, CFG)
    assert f["W"] is None


def test_scroll_reversals():
    m = [[0, 10, 10, "empty"]]
    s = [[100, 0, "empty"], [200, 100, "empty"], [300, 200, "empty"], [400, 100, "empty"], [500, 200, "empty"], [600, 100, "empty"]]
    f = features_at(Timeline(m, s), 700, CFG)
    assert f["S"] == 3


def test_live_and_offline_give_identical_features():
    import random
    rng = random.Random(3)
    m, t = [], 0
    for _ in range(600):
        t += rng.choice([16, 16, 16, 40, 300])
        m.append([t, rng.randint(0, 1300), rng.randint(0, 800), rng.choice(["card:A", "card:B", "spec:A:battery", "empty", "read:card"])])
    s = [[k * 700, (k % 3) * 100, "empty"] for k in range(1, 20)]
    off = Timeline(m, s)
    live = Timeline()
    for i in range(0, len(m), 25):            # batches as the browser sends them
        lo, hi = m[i][0], m[min(i + 24, len(m) - 1)][0]
        live.add(m[i:i + 25], [e for e in s if lo <= e[0] <= hi and e not in live_s(live)])
    for tt in range(500, t, 500):
        a, b = features_at(off, tt, CFG), features_at(live, tt, CFG)
        assert {k: a[k] for k in "BFIWS"} == {k: b[k] for k in "BFIWS"}


def live_s(tl):
    return [[t, y] for t, y in zip(tl.ST, tl.SY)]


def test_robust_stats_and_zscores():
    med, spread = robust_stats([0, 0, 1, 1, 2, 10])
    assert med == 1 and abs(spread - 1.4826) < 1e-6
    base = {s: {"median": 0.0, "spread": 0.0} for s in "BFIWS"}
    z, floored = zscores({"B": 3, "F": 0.0, "I": 0.2, "W": None, "S": 0}, base, CFG)
    assert z["B"] == min(5.0, 3 / CFG["min_spread"]["B"])
    assert z["W"] == 0.0 and z["F"] == 0.0
    assert "B" in floored
    neg, _ = zscores({"B": 0, "F": 0.0, "I": 0.0, "W": 0.5, "S": 0}, {s: {"median": 1.0, "spread": 1.0} for s in "BFIWS"}, CFG)
    assert all(v == 0 for v in neg.values())          # negatives set to 0


def test_detector_scores_and_type():
    z = {"B": 5.0, "F": 4.0, "I": 0.0, "W": 1.0, "S": 0.0}
    sc = detector_scores(z)
    assert sc["avg"] == 2.0 and sc["max"] == 5.0
    assert predicted_type(z) == "compare"
    assert predicted_type({"B": 0, "F": 3, "I": 1, "W": 0, "S": 0}) == "explain"
    assert predicted_type({s: 0.0 for s in "BFIWS"}) == "general"


def tick(t, score, seen=True):
    return {"t": t, "scores": {"avg": score, "max": score, "B": score, "I": score}, "seen": seen, "z": {}}


def test_trigger_needs_persistence_seen_and_respects_cooldown_and_max():
    ticks = [tick(500 * k, 2.0, seen=k >= 3) for k in range(1, 400)]
    fired = simulate(ticks, CFG, threshold=1.5)
    assert fired[0] == 500 * 4                       # 4 checks above + seen from tick 3
    assert all(b - a >= CFG["cooldown_s"] * 1000 for a, b in zip(fired, fired[1:]))
    assert len(fired) == CFG["max_popups"]
    assert simulate([tick(500 * k, 2.0 if k % 4 else 0.0) for k in range(1, 200)], CFG, threshold=1.5) == []


def test_dismiss_doubles_cooldown():
    rule = TriggerRule(CFG, threshold=1.0)
    fired = []
    for k in range(1, 400):
        if rule.step(tick(500 * k, 2.0)):
            fired.append(500 * k)
            rule.open = True
            rule.popup_closed(dismissed=True)
    assert fired[1] - fired[0] >= CFG["dismiss_cooldown_s"] * 1000


def test_seen_tracker():
    m = []
    t = 0
    for c in "ABCD":
        for _ in range(70):
            t += 16
            m.append([t, 0, 0, f"card:{c}"])
    tl = Timeline(m, [])
    st = SeenTracker(list("ABCD"), 1000)
    assert not st.update(tl, 3000)
    assert st.update(tl, t)


def test_latin_square_blocks_are_balanced():
    slots = _make_blocks(6, seed=1)
    for b in range(6):
        block = slots[4 * b: 4 * b + 4]
        pos = {c: set() for c in COND_CODES}
        pair = set()
        for sl in block:
            conds = [COND_CODES[i] for i in WILLIAMS_ROWS[sl["cond_row"]]]
            sets = [MAIN_SETS[i] for i in CYCLIC_ROWS[sl["set_row"]]]
            for p, (c, s) in enumerate(zip(conds, sets)):
                pos[c].add(p)
                pair.add((c, s))
        assert all(len(v) == 4 for v in pos.values())     # each condition once in each position
        assert len(pair) == 16                             # each condition paired with each set once


def test_williams_square_first_order_balance():
    follows = {}
    for row in WILLIAMS_ROWS:
        for a, b in zip(row, row[1:]):
            follows[(a, b)] = follows.get((a, b), 0) + 1
    assert all(v == 1 for v in follows.values()) and len(follows) == 12


def test_score_triggers_and_rule():
    s = score_triggers([1000, 9000, 30000], [[2000, 5000], [8000, 10000]], 3000)
    assert s["hits"] == 2 and s["false_alarms"] == 1 and s["caught"] == 2
    rows = [{"threshold": 1.0, "precision": 0.6, "recall": 0.9, "fa_per_task": 0.5},
            {"threshold": 1.5, "precision": 0.72, "recall": 0.70, "fa_per_task": 0.6},
            {"threshold": 1.75, "precision": 0.8, "recall": 0.69, "fa_per_task": 0.3},
            {"threshold": 2.0, "precision": 0.9, "recall": 0.5, "fa_per_task": 0.2}]
    assert choose_threshold(rows) == 1.75          # 1.5 and 1.75 almost equal recall -> higher threshold
    assert choose_threshold([{"threshold": 1.0, "precision": 0.5, "recall": 0.9, "fa_per_task": 2}]) is None
