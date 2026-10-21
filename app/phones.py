"""Phone sets: loading, correctness and rank of a choice."""
import json
from functools import lru_cache

from .config import DATA_DIR


@lru_cache(maxsize=1)
def catalog():
    with open(DATA_DIR / "phone_sets.json", encoding="utf-8") as f:
        return json.load(f)


def get_set(set_id):
    return catalog()["sets"][set_id]


def phone(set_id, phone_id):
    for p in get_set(set_id)["phones"]:
        if p["id"] == phone_id:
            return p
    return None


def score_choice(set_id, phone_id, task_kind):
    """Return (correct, rank) for a choice. Baseline/practice tasks use the 'answers' map."""
    s = get_set(set_id)
    if set_id == "P":
        ans = s["answers"].get(task_kind)
        return (phone_id == ans, 1 if phone_id == ans else None)
    p = phone(set_id, phone_id)
    if p is None:
        return (False, None)
    return (p.get("rank") == 1, p.get("rank"))


def public_set(set_id):
    """What the browser may see: no roles or ranks (so answers cannot be read from the page)."""
    s = get_set(set_id)
    phones = [{k: v for k, v in p.items() if k not in ("role", "rank")} for p in s["phones"]]
    return {"id": set_id, "card": s["card"], "phones": phones, "spec_labels": catalog()["spec_labels"]}
