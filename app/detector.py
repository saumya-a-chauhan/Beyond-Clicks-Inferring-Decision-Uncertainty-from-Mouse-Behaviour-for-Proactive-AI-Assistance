"""Trigger rules (section 5, step 6 of the protocol). Shared by live use and offline simulation.

A tick = one check every tick_ms. For each tick we store the raw signs, z-scores, the 4 detector
scores and whether all phones have been seen. `TriggerRule` decides when a pop-up fires.
"""
import random

from .features import SeenTracker, Timeline, detector_scores, features_at, predicted_type, zscores


def make_tick(tl, t, base, cfg, seen):
    f = features_at(tl, t, cfg)
    z, floored = zscores(f, base, cfg)
    sc = detector_scores(z)
    return {
        "t": t,
        "raw": {k: f[k] for k in ("B", "F", "I", "W", "S")},
        "z": z,
        "scores": sc,
        "seen": seen,
        "pair": f["pair"],
        "spec": f["spec"],
        "floored": floored,
    }


def compute_ticks(m, s, phone_ids, base, cfg, t_end):
    """Offline: all ticks of a finished task."""
    tl = Timeline(m, s)
    seen = SeenTracker(phone_ids, cfg["seen_card_ms"])
    ticks = []
    t = cfg["tick_ms"]
    while t <= t_end:
        ticks.append(make_tick(tl, t, base, cfg, seen.update(tl, t)))
        t += cfg["tick_ms"]
    return ticks


class TriggerRule:
    """mode: 'detector' (C3) or 'random' (C4). For offline simulation pop-ups close instantly."""

    def __init__(self, cfg, mode="detector", variant="avg", threshold=None, seed=0):
        self.cfg = cfg
        self.mode = mode
        self.variant = variant
        self.thr = cfg["threshold"] if threshold is None else threshold
        self.run = 0
        self.fired = []          # list of fire times
        self.last_fire = None
        self.last_dismissed = False
        self.open = False
        self.rng = random.Random(seed)

    def blocked(self, t):
        if self.open or len(self.fired) >= self.cfg["max_popups"]:
            return True
        if self.last_fire is not None:
            cd = self.cfg["dismiss_cooldown_s"] if self.last_dismissed else self.cfg["cooldown_s"]
            if t - self.last_fire < cd * 1000:
                return True
        return False

    def step(self, tick):
        """Return True if a pop-up should fire at this tick."""
        t = tick["t"]
        above = tick["scores"][self.variant] >= self.thr
        self.run = self.run + 1 if above else 0
        if not tick["seen"] or self.blocked(t):
            return False
        if self.mode == "random":
            p = self.cfg["c4_rate_per_min"] * self.cfg["tick_ms"] / 60000.0
            fire = self.rng.random() < p
        else:
            fire = self.run >= self.cfg["persistence_ticks"]
        if fire:
            self.fired.append(t)
            self.last_fire = t
            self.last_dismissed = False
        return fire

    def popup_closed(self, dismissed):
        self.open = False
        self.last_dismissed = bool(dismissed)


def simulate(ticks, cfg, variant="avg", threshold=None, mode="detector", seed=0):
    rule = TriggerRule(cfg, mode=mode, variant=variant, threshold=threshold, seed=seed)
    return [tk["t"] for tk in ticks if rule.step(tk)]


def popup_content(tick, mode, rng=None):
    """What the pop-up offers. Detector: from the biggest sign. Random: random type."""
    if mode == "random":
        rng = rng or random
        ptype = rng.choice(["compare", "explain", "general"])
    else:
        ptype = predicted_type(tick["z"])
    return {"predicted_type": ptype, "pair": tick.get("pair"), "spec": tick.get("spec")}
