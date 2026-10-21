"""Cursor features ("signs") for hesitation detection.

One implementation is used everywhere: live during the study (app/live.py) and offline in the
pilot / main analysis (app/analysis.py). So the threshold chosen on pilot data is applied to
exactly the same numbers in the main study.

Event formats (logged by the browser, times in ms since task start):
  mouse  m: [t, clientX, clientY, zone]
  scroll s: [t, scrollY, zone_under_cursor]
Zones: "card:<phone>", "spec:<phone>:<spec>", "read:card", "read:details", "ui:*", "empty".

The 5 signs, measured over the last `window_ms` at time t (see docs/DETECTOR.md):
  B  back-and-forth: switches between phone cards (visits >= visit_min_ms)
  F  freezing: longest rest on one spec row (s, max window)
  I  pausing: longest rest in empty space (s, max window)
  W  wandering: path length / straight distance of moves between rest points (None if no move)
  S  scroll flip-flops: scroll direction reversals
"""
from bisect import bisect_right, insort
from math import hypot
from statistics import median

from .defaults import SIGNS


def card_of(zone):
    if not zone:
        return None
    if zone.startswith("card:"):
        return zone[5:]
    if zone.startswith("spec:"):
        return zone.split(":")[1]
    return None


class Timeline:
    """Cursor positions + zones over time for one task. Supports adding events in batches."""

    def __init__(self, m=None, s=None):
        self.T, self.X, self.Y, self.Z = [], [], [], []
        self.ST, self.SY = [], []
        if m or s:
            self.add(m or [], s or [])

    def _insert(self, t, x, y, z):
        if not self.T or t >= self.T[-1]:
            self.T.append(t); self.X.append(x); self.Y.append(y); self.Z.append(z)
        else:
            i = bisect_right(self.T, t)
            self.T.insert(i, t); self.X.insert(i, x); self.Y.insert(i, y); self.Z.insert(i, z)

    def add(self, m, s):
        pts = [(e[0], 0, e[1], e[2], e[3]) for e in m] + [(e[0], 1, None, None, e[2]) for e in s]
        pts.sort(key=lambda p: (p[0], p[1]))
        for t, kind, x, y, z in pts:
            if kind == 1:
                i = bisect_right(self.T, t) - 1
                if i < 0:
                    continue
                x, y = self.X[i], self.Y[i]
            self._insert(t, x, y, z)
        for e in s:
            if not self.ST or e[0] >= self.ST[-1]:
                self.ST.append(e[0]); self.SY.append(e[1])
            else:
                i = bisect_right(self.ST, e[0])
                self.ST.insert(i, e[0]); self.SY.insert(i, e[1])

    def segments(self, t_from, t):
        """Segments overlapping [t_from, t]. The cursor stays at point i until point i+1.
        A segment that is cut at t has speed 0: at time t we do not yet know the next point
        (keeps live and offline results identical)."""
        T, X, Y, Z = self.T, self.X, self.Y, self.Z
        n = len(T)
        i1 = bisect_right(T, t) - 1
        if i1 < 0:
            return []
        i0 = max(0, bisect_right(T, t_from) - 1)
        out = []
        for i in range(i0, i1 + 1):
            s0 = T[i]
            if i + 1 < n and T[i + 1] <= t:
                e0 = T[i + 1]
                d = hypot(X[i + 1] - X[i], Y[i + 1] - Y[i])
                dt = (e0 - s0) / 1000.0
                spd = d / dt if dt > 0 else (float("inf") if d > 0 else 0.0)
            else:
                e0, d, spd = t, 0.0, 0.0
            out.append((s0, e0, d, spd, Z[i], X[i], Y[i]))
        return out


def _overlap(a, b, lo, hi):
    return max(0.0, min(b, hi) - max(a, lo))


def features_at(tl, t, cfg):
    W = cfg["window_ms"]
    lo = t - W
    segs = tl.segments(t - W - cfg["lookback_ms"], t)
    out = {"B": 0, "F": 0.0, "I": 0.0, "W": None, "S": 0, "pair": None, "spec": None}
    if not segs:
        return out
    rest_v = cfg["rest_speed_px_s"]

    # --- F and I: rest runs in the same zone ---
    best_f, best_i, spec = 0.0, 0.0, None
    run_zone, run_s, run_e = None, None, None

    def close_run():
        nonlocal best_f, best_i, spec
        if run_zone is None:
            return
        ov = _overlap(run_s, run_e, lo, t)
        if run_zone.startswith("spec:") and ov > best_f:
            best_f, spec = ov, run_zone
        elif run_zone == "empty" and ov > best_i:
            best_i = ov

    for s0, e0, d, spd, z, x, y in segs:
        if spd < rest_v and z:
            if z == run_zone and s0 <= run_e:
                run_e = e0
                continue
            close_run()
            run_zone, run_s, run_e = z, s0, e0
        else:
            close_run()
            run_zone = None
    close_run()
    out["F"] = min(best_f, W) / 1000.0
    out["I"] = min(best_i, W) / 1000.0
    out["spec"] = spec.split(":")[2] if spec else None

    # --- B: switches between valid card visits ---
    visits = []  # [card, start, dur]
    dwell = {}
    for s0, e0, d, spd, z, x, y in segs:
        c = card_of(z)
        if c is None:
            continue
        dur = e0 - s0
        dwell[c] = dwell.get(c, 0.0) + _overlap(s0, e0, t - cfg["lookback_ms"], t)
        if visits and visits[-1][0] == c:
            visits[-1][2] += dur
        else:
            visits.append([c, s0, dur])
    valid = [v for v in visits if v[2] >= cfg["visit_min_ms"]]
    b = 0
    for prev, cur in zip(valid, valid[1:]):
        if cur[0] != prev[0] and lo < cur[1] <= t:
            b += 1
    out["B"] = b
    top = sorted(dwell.items(), key=lambda kv: -kv[1])
    if len(top) >= 2:
        out["pair"] = [top[0][0], top[1][0]]

    # --- W: path / straight distance of moves between rest points ---
    rps = []  # (first_seg_idx, last_seg_idx)
    k, n = 0, len(segs)
    while k < n:
        if segs[k][3] < rest_v:
            j = k
            while j + 1 < n and segs[j + 1][3] < rest_v:
                j += 1
            if segs[j][1] - segs[k][0] >= cfg["rest_point_ms"]:
                rps.append((k, j))
            k = j + 1
        else:
            k += 1
    path_sum, straight_sum = 0.0, 0.0
    for (a0, b0), (a1, b1) in zip(rps, rps[1:]):
        if b0 + 1 >= a1:
            continue
        end_t = segs[a1][0]
        if not (lo < end_t <= t):
            continue
        sx, sy = segs[b0 + 1][5], segs[b0 + 1][6]
        ex, ey = segs[a1][5], segs[a1][6]
        straight = hypot(ex - sx, ey - sy)
        if straight < cfg["min_move_px"]:
            continue
        path_sum += sum(segs[q][2] for q in range(b0 + 1, a1))
        straight_sum += straight
    out["W"] = (path_sum / straight_sum) if straight_sum > 0 else None

    # --- S: scroll direction reversals ---
    ST, SY = tl.ST, tl.SY
    j0 = max(1, bisect_right(ST, t - W - cfg["lookback_ms"]))
    j1 = bisect_right(ST, t)
    last_sign, rev = 0, 0
    for j in range(j0, j1):
        dlt = SY[j] - SY[j - 1]
        if dlt == 0:
            continue
        sg = 1 if dlt > 0 else -1
        if last_sign and sg != last_sign and lo < ST[j] <= t:
            rev += 1
        last_sign = sg
    out["S"] = rev
    return out


class SeenTracker:
    """When has every phone card been hovered for >= seen_card_ms in total?"""

    def __init__(self, phone_ids, need_ms):
        self.need = need_ms
        self.acc = {p: 0.0 for p in phone_ids}
        self.done_at = None
        self.pos = 0

    def update(self, tl, t):
        if self.done_at is not None:
            return self.done_at <= t
        T, Z = tl.T, tl.Z
        n = len(T)
        while self.pos < n and T[self.pos] <= t:
            i = self.pos
            nxt = T[i + 1] if i + 1 < n else None
            if nxt is None or nxt > t:
                break  # last segment still open; count it next time
            c = card_of(Z[i])
            if c in self.acc:
                before = self.acc[c]
                self.acc[c] += nxt - T[i]
                if before < self.need <= self.acc[c] and all(v >= self.need for v in self.acc.values()):
                    self.done_at = T[i] + (self.need - before)
                    return self.done_at <= t
            self.pos += 1
        # include the open segment for the check, without committing it
        if self.pos < n and T[self.pos] <= t:
            c = card_of(Z[self.pos])
            if c in self.acc:
                extra = t - T[self.pos]
                if all((v + (extra if p == c else 0)) >= self.need for p, v in self.acc.items()):
                    return True
        return False


def robust_stats(values):
    """Median and 1.4826 * MAD (the 'modified z-score' spread, Iglewicz & Hoaglin 1993)."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None, None
    med = median(vals)
    mad = median(abs(v - med) for v in vals)
    return med, 1.4826 * mad


def baseline_stats(timelines, cfg):
    """timelines: list of (Timeline, t_end_ms). Returns {sign: {"median", "spread", "n"}}."""
    vals = {s: [] for s in SIGNS}
    for tl, t_end in timelines:
        t = cfg["window_ms"]
        while t <= t_end:
            f = features_at(tl, t, cfg)
            for s in SIGNS:
                vals[s].append(f[s])
            t += cfg["tick_ms"]
    out = {}
    for s in SIGNS:
        med, spread = robust_stats(vals[s])
        out[s] = {"median": med if med is not None else 0.0,
                  "spread": spread if spread is not None else 0.0,
                  "n": len([v for v in vals[s] if v is not None])}
    return out


def zscores(feat, base, cfg):
    """Per-person modified z-scores, negatives set to 0, capped at z_cap.
    Returns (z dict, list of signs where the minimum spread was used)."""
    z, floored = {}, []
    for s in SIGNS:
        v = feat[s]
        if v is None:
            z[s] = 0.0
            continue
        b = base.get(s, {"median": 0.0, "spread": 0.0})
        spread = b["spread"]
        floor = cfg["min_spread"][s]
        if spread < floor:
            spread = floor
            floored.append(s)
        val = (v - b["median"]) / spread
        z[s] = max(0.0, min(cfg["z_cap"], val))
    return z, floored


def detector_scores(z):
    """The main detector (average of 5 z) and the 3 comparison detectors."""
    return {
        "avg": sum(z[s] for s in SIGNS) / len(SIGNS),
        "max": max(z[s] for s in SIGNS),
        "B": z["B"],
        "I": z["I"],
    }


def predicted_type(z):
    best = max(SIGNS, key=lambda s: (z[s], s == "B", s == "F"))
    if z[best] <= 0:
        return "general"
    if best == "B":
        return "compare"
    if best == "F":
        return "explain"
    return "general"
