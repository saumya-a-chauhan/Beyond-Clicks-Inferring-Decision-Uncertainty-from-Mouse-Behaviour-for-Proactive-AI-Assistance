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
    """mode: 'detector' (C3) or 'random' (C4). For offline simulation pop-ups close instantly.

    Main stage: C3 fires when the score has been >= threshold for persistence_ticks checks; C4 fires at random
    with c4_rate_per_min. Extra stage (extra=True, the at-least-once rule): if a round has had no pop-up
    extra_after_s seconds after phones were seen, C3 fires at the first check with score >= extra_threshold
    and C4 fires at that same moment without looking at the score. Compulsory stage: if no pop-up has fired
    by compulsory_s seconds in an AI round, C3 and C4 fire compulsorily to guarantee AI assistance."""

    def __init__(self, cfg, mode="detector", variant="avg", threshold=None, seed=0, extra=False):
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
        self.extra = extra and cfg.get("extra_after_s") is not None
        self.compulsory_s = cfg.get("compulsory_s", 12)
        self.seen_at = None
        self.stage = None        # stage of the last pop-up: "main", "extra", or "compulsory"

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
        score = tick["scores"][self.variant]
        self.run = self.run + 1 if score >= self.thr else 0
        if tick["seen"] and self.seen_at is None:
            self.seen_at = t

        if self.blocked(t):
            return False

        if self.mode == "random":
            p = self.cfg["c4_rate_per_min"] * self.cfg["tick_ms"] / 60000.0
            fire = self.rng.random() < p
        else:
            fire = tick["seen"] and (self.run >= self.cfg["persistence_ticks"])

        self.stage = "main"

        # At-least-once rule
        if not fire and self.extra and not self.fired:
            if self.seen_at is not None and t - self.seen_at >= self.cfg.get("extra_after_s", 8) * 1000:
                fire = self.mode == "random" or score >= self.cfg.get("extra_threshold", 0.8)
                self.stage = "extra"
            # Compulsory fallback: guarantee AI triggers in AI round
            if not fire and self.compulsory_s and t >= self.compulsory_s * 1000:
                fire = True
                self.stage = "compulsory"

        if fire:
            self.fired.append(t)
            self.last_fire = t
            self.last_dismissed = False
        return fire

    def popup_closed(self, dismissed):
        self.open = False
        self.last_dismissed = bool(dismissed)


def simulate(ticks, cfg, variant="avg", threshold=None, mode="detector", seed=0, extra=False, stages=False):
    """Pop-up times for a finished round (stages=True: (time, "main" | "extra") pairs)."""
    rule = TriggerRule(cfg, mode=mode, variant=variant, threshold=threshold, seed=seed, extra=extra)
    out = [(tk["t"], rule.stage) for tk in ticks if rule.step(tk)]
    return out if stages else [t for t, _ in out]


def popup_content(tick, mode, rng=None):
    """What the pop-up offers. Detector: from the biggest sign. Random: random type."""
    if mode == "random":
        rng = rng or random
        ptype = rng.choice(["compare", "explain", "general"])
    else:
        ptype = predicted_type(tick["z"])
    return {"predicted_type": ptype, "pair": tick.get("pair"), "spec": tick.get("spec")}
