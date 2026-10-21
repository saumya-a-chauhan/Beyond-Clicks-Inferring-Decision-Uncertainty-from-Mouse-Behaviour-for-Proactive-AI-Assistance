"""Counterbalancing: balanced Latin square with permuted blocks.

Main study: each block of 4 participants gets the 4 Williams-square condition orders in a random
order, and one cyclic row for phone sets. Within every block each condition appears once in each
position and is paired with each phone set once, so balance holds after every 4 participants.

Pilot: no AI, so only the phone-set order is counterbalanced (cyclic rows in random blocks).
"""
import random

from sqlalchemy import select

from . import db
from .defaults import COND_CODES, CYCLIC_ROWS, MAIN_SETS, WILLIAMS_ROWS


def _make_blocks(n_blocks, seed=None):
    rng = random.Random(seed)
    slots = []
    for b in range(n_blocks):
        rows = list(range(4))
        rng.shuffle(rows)
        set_row = b % 4
        for r in rows:
            slots.append({"cond_row": r, "set_row": set_row})
    return slots


def _pilot_blocks(n_blocks, seed=None):
    rng = random.Random(seed)
    slots = []
    for _ in range(n_blocks):
        rows = list(range(4))
        rng.shuffle(rows)
        slots.extend({"set_row": r} for r in rows)
    return slots


def next_assignment(conn, study):
    """Take the next slot (stored in settings so it survives restarts). Returns (slot, cond_order, set_order)."""
    key = f"assignment_{study}"
    row = conn.execute(select(db.settings_t.c.value).where(db.settings_t.c.key == key)).first()
    state = db.loads(row[0]) if row else None
    if state is None or state["next"] >= len(state["slots"]):
        seed = random.SystemRandom().randrange(1 << 30)
        new = _make_blocks(12, seed) if study == "main" else _pilot_blocks(12, seed)
        if state is None:
            state = {"slots": new, "next": 0, "seeds": [seed]}
        else:
            state["slots"].extend(new)
            state["seeds"].append(seed)
    slot_no = state["next"]
    slot = state["slots"][slot_no]
    state["next"] += 1
    db.set_setting(key, state, conn=conn)
    set_order = [MAIN_SETS[i] for i in CYCLIC_ROWS[slot["set_row"]]]
    if study == "main":
        cond_order = [COND_CODES[i] for i in WILLIAMS_ROWS[slot["cond_row"]]]
    else:
        cond_order = ["C1", "C1", "C1", "C1"]
    return slot_no, cond_order, set_order
