"""Live detector state for tasks in progress (kept in memory, rebuilt from the database if the
server restarted in the middle of a task)."""
import threading

from sqlalchemy import select

from . import db
from .detector import TriggerRule, make_tick
from .features import SeenTracker, Timeline

MODE = {"C3": "detector", "C4": "random"}
MAX_TICKS_PER_CALL = 40


class LiveTask:
    def __init__(self, task_id, condition, phone_ids, base, cfg):
        self.task_id = task_id
        self.cfg = cfg
        self.base = base
        self.tl = Timeline()
        self.seen = SeenTracker(phone_ids, cfg["seen_card_ms"])
        mode = MODE.get(condition)
        self.rule = TriggerRule(cfg, mode=mode, seed=task_id, extra=True) if mode else None
        self.next_tick = cfg["tick_ms"]
        self.last_tick = None
        self.lock = threading.Lock()

    def add(self, m, s):
        self.tl.add(m, s)

    def process(self, now_ms):
        """Run all checks up to now. Returns the tick at which a pop-up fired, or None."""
        fired = None
        if now_ms - self.next_tick > MAX_TICKS_PER_CALL * self.cfg["tick_ms"]:
            # far behind (e.g. after a reconnect): skip ahead instead of firing on stale data
            self.next_tick = now_ms - MAX_TICKS_PER_CALL * self.cfg["tick_ms"]
            self.next_tick -= self.next_tick % self.cfg["tick_ms"]
        while self.next_tick <= now_ms:
            tk = make_tick(self.tl, self.next_tick, self.base, self.cfg, self.seen.update(self.tl, self.next_tick))
            tk["seen_at"] = self.seen.done_at          # exact all-seen time, also right after a rebuild
            if self.rule is not None:
                did = self.rule.step(tk)
                if did and fired is None:
                    fired = tk
                    self.rule.open = True
            self.last_tick = tk
            self.next_tick += self.cfg["tick_ms"]
        return fired

    def popup_closed(self, dismissed):
        if self.rule is not None:
            self.rule.popup_closed(dismissed)


_tasks = {}
_glock = threading.Lock()


def get(task_id, loader):
    """loader() -> (condition, phone_ids, base, cfg). Rebuilds state from stored events if needed.
    Returns (LiveTask, rebuilt) - rebuilt=True means all stored events (incl. the latest batch) are loaded."""
    with _glock:
        lt = _tasks.get(task_id)
        if lt is not None:
            return lt, False
        condition, phone_ids, base, cfg = loader()
        lt = LiveTask(task_id, condition, phone_ids, base, cfg)
        with db.engine.connect() as c:
            ev = db.task_events(c, task_id)
            prev = popups_so_far(c, task_id)
        lt.add(ev["m"], ev["s"])
        restore(lt, prev)
        last_t = max([e[0] for e in ev["m"]] + [e[0] for e in ev["s"]] + [0])
        lt.next_tick = max(cfg["tick_ms"], last_t - last_t % cfg["tick_ms"])
        _tasks[task_id] = lt
        return lt, True


def popups_so_far(conn, task_id):
    return conn.execute(select(db.popups.c.t_ms, db.popups.c.choice, db.popups.c.closed_ms)
                        .where(db.popups.c.task_id == task_id).order_by(db.popups.c.t_ms)).all()


def restore(lt, prev):
    """Pop-ups already shown in this round (from the database): the only state the rule needs between requests.
    Called on every request, because on a serverless host another instance may have shown one meanwhile."""
    if lt.rule is None:
        return
    r = lt.rule
    r.fired, r.last_fire, r.last_dismissed, r.open = [], None, False, False
    for t_ms, choice, closed in prev:
        r.fired.append(t_ms)
        r.last_fire = t_ms
        r.last_dismissed = choice == "dismiss"
        r.open = closed is None and choice is None


def drop(task_id):
    with _glock:
        _tasks.pop(task_id, None)
