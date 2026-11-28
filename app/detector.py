"""Trigger rules (section 5, step 6 of the protocol). Shared by live use and offline simulation.

A tick = one check every tick_ms. For each tick we store the raw signs, z-scores, the 4 detector
scores and whether all phones have been seen. `TriggerRule` decides when a pop-up fires.
"""
import random

from .defaults import YOKED_DELAYS_S
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
    """When a pop-up fires. mode 'detector' = Smart (C3), 'random' = Random (C4). Pop-ups close instantly offline.

    Smart:  main  - all phones seen and score >= threshold for persistence_ticks checks.
            extra - (extra=True) no pop-up yet, extra_after_s since all phones were seen, score >= extra_threshold.
    Random: yoked - (extra=True) first pop-up at all-seen + a delay drawn for this round from YOKED_DELAYS_S
                    (Smart's own pilot delays), score not used.
            main  - later pop-ups at random, c4_rate_per_min.
    Both:   cooldown and max_popups. The at-Buy pop-up (no pop-up before Buy) is added by the server.

    Nothing depends on memory between requests except the pop-ups already shown, which the server restores from
    the database: every random draw is fixed by the round's seed and the check's time, and the all-seen time comes
    from the tick. So a rule rebuilt on a fresh serverless instance decides exactly like a long-lived one."""

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
        self.seed = seed
        self.extra = extra
        self.seen_at = None
        self.stage = None        # stage of the last pop-up: main, extra or yoked
        self.delay_ms = int(random.Random(seed).choice(YOKED_DELAYS_S) * 1000)

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
            self.seen_at = tick.get("seen_at") or t
        if not tick["seen"] or self.blocked(t):
            return False
        since = t - self.seen_at
        if self.mode == "random":
            if self.extra and not self.fired:
                fire, stage = since >= self.delay_ms, "yoked"
            else:
                p = self.cfg["c4_rate_per_min"] * self.cfg["tick_ms"] / 60000.0
                fire, stage = random.Random(self.seed * 1_000_003 + t).random() < p, "main"
        else:
            fire, stage = self.run >= self.cfg["persistence_ticks"], "main"
            if (not fire and self.extra and not self.fired and since >= self.cfg["extra_after_s"] * 1000
                    and score >= self.cfg["extra_threshold"]):
                fire, stage = True, "extra"
        if fire:
            self.stage = stage
            self.fired.append(t)
            self.last_fire = t
            self.last_dismissed = False
        return fire

    def popup_closed(self, dismissed):
        self.open = False
        self.last_dismissed = bool(dismissed)


def simulate(ticks, cfg, variant="avg", threshold=None, mode="detector", seed=0, extra=False, stages=False):
    """Pop-up times for a finished round (stages=True: (time, stage) pairs)."""
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
