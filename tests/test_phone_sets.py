"""Every main phone set is a real trade-off with one defensible correct answer (see the _note in phone_sets.json)."""
import json
import re

from app.phones import catalog, public_set

# Priority -> (hidden true value, True if higher is better)
MEASURE = {
    ("S1", "battery"): ("battery_h", True), ("S1", "camera"): ("lowlight_lux", False),
    ("S2", "camera"): ("zoom_x", True), ("S2", "display"): ("nits", True),
    ("S3", "storage"): ("free_gb", True), ("S3", "display"): ("nits", True),
    ("S4", "chip"): ("sustained", True), ("S4", "battery"): ("gaming_battery_h", True),
    ("S5", "battery"): ("battery_h", True), ("S5", "storage"): ("free_gb", True),
}
SETS = ["S1", "S2", "S3", "S4", "S5"]


def _better(a, b, key, higher):
    return a["_truth"][key] > b["_truth"][key] if higher else a["_truth"][key] < b["_truth"][key]


def _by_role(s):
    return {p["role"]: p for p in s["phones"]}


def test_no_summary_scores_anywhere():
    text = json.dumps(catalog(), ensure_ascii=False)
    assert not re.search(r"\d+\s*/\s*100", text), "no 'x / 100' scores may be shown"
    assert "score" not in " ".join(d[0].lower() for s in catalog()["sets"].values() for p in s["phones"] for d in p["details"])


def test_structure_and_hidden_values():
    for sid in SETS:
        s = catalog()["sets"][sid]
        roles = _by_role(s)
        assert set(roles) == {"correct", "trap_main", "trap_second", "dominated"}, sid
        assert [roles[r]["rank"] for r in ("correct", "trap_main", "trap_second", "dominated")] == [1, 2, 3, 4], sid
        for p in public_set(sid)["phones"]:
            assert "_truth" not in p and "rank" not in p and "role" not in p, sid


def test_correct_phone_and_real_trade_off():
    for sid in SETS:
        s = catalog()["sets"][sid]
        p1, p2 = s["card"]["priorities"][:2]
        k1, h1 = MEASURE[(sid, p1)]
        k2, h2 = MEASURE[(sid, p2)]
        budget = s["card"]["budget"]
        r = _by_role(s)
        in_budget = [p for p in s["phones"] if p["_truth"]["price"] <= budget]
        assert r["trap_second"]["_truth"]["price"] > budget, f"{sid}: second trap should be over budget"
        best = max(in_budget, key=lambda p: p["_truth"][k1] if h1 else -p["_truth"][k1])
        assert best["role"] == "correct", f"{sid}: correct phone must win Priority 1 within budget"
        # real trade-off: the main trap beats the correct phone on Priority 2
        assert _better(r["trap_main"], r["correct"], k2, h2), f"{sid}: main trap must win Priority 2"
        # dominated: worse than the correct phone on every measured value, same price or more
        d, a = r["dominated"], r["correct"]
        assert d["_truth"]["price"] >= a["_truth"]["price"], sid
        for key in a["_truth"]:
            if key in ("price", "amoled", "peak"):
                continue
            higher = not key.endswith("_lux")
            assert _better(a, d, key, higher), f"{sid}: dominated phone must be worse on {key}"


def test_measured_values_are_in_the_specs():
    """The shopping screen shows only the specs ('View details'), so every measured value must be there:
    the lab table and reviews are shown only after the first choice."""
    for sid, s in catalog()["sets"].items():
        for p in s["phones"]:
            text = " ".join(p["specs"].values())
            for _, value in p["details"]:
                assert value in text, (sid, p["id"], value)


def test_every_phone_has_its_own_design():
    keys = ("camera", "shape", "finish", "notch", "wallpaper")
    designs = []
    for sid, s in catalog()["sets"].items():
        looks = [p["look"] for p in s["phones"]]
        assert all(set(lk) == set(keys) for lk in looks), sid
        for k in ("camera", "shape", "finish", "notch", "wallpaper"):
            assert len({lk[k] for lk in looks}) == len(looks), (sid, k)      # within a set, every part differs
        designs += [tuple(lk[k] for k in keys) for lk in looks]
    assert len(set(designs)) == len(designs)                                 # no two phones look the same
