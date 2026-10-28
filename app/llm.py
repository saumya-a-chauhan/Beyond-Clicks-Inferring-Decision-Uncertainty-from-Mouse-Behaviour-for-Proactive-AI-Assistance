"""AI help: Gemini first, Groq if Gemini fails, and a written fallback if both fail.

Answers are grounded ONLY in the phone data of the current set, and cached: the same request
(same set, same help type, same phones/spec) always gets the same text, so every participant in
every condition sees identical help content (experimental control), and it is fast and cheap.
"""
import hashlib
import json
import os
import re
import time

import httpx
from sqlalchemy import select

from . import config, db
from .phones import catalog, get_set

SYSTEM = (
    "You are a shopping assistant inside a research study about choosing phones. "
    "Use ONLY the phone data provided below; never invent or guess specs, prices or test results. "
    "If something is not in the data, say you do not have that information. "
    "Explain trade-offs in plain, friendly English for a non-technical buyer, relating them to the buyer's stated needs. "
    "Use the lab test results to explain what the headline numbers really mean; convert values given in different units (minutes and hours; GB, TB and MB; millions and Indian lakhs) to the same unit before comparing, and remember that lower lux and lower f-numbers are better. "
    "Do NOT tell the buyer which phone to buy and do not rank the phones; help them understand so they can decide. "
    "Keep it under 110 words. Write numbers as digits with their units (for example 12 h 40 min, 2 lux, Rs 24,999). Plain text only: no markdown, no headings, no bold. "
    "Use 3 to 5 short lines, each starting with '- '."
)

GLOSSARY = {
    "battery": "mAh is the battery's size, not how long it lasts: an efficient chip (smaller nm) and screen matter as much. Compare the lab screen-on times, and convert them to the same unit first: 760 minutes is 12 h 40 min, and 13 h 50 min is 830 minutes.",
    "chip": "The first AnTuTu run shows peak speed, but phones that get hot slow down in long games. 'Keeps 88% of its speed after 30 min' or 'drops to 0.61x' tells you the speed in a long session: multiply the first-run score by it. Indian number format: 14,50,000 is 1.45 million and 8,20,000 is 0.82 million. 'Gaming Mode' and more RAM do not make a phone faster.",
    "display": "AMOLED screens have deeper blacks and richer colours than LCD. Hz is scrolling smoothness. Nits and cd/m2 are the same unit of brightness: higher is easier to see in sunlight, so 1,800 cd/m2 is brighter than 1,200 nits.",
    "camera": "Megapixels (MP) are resolution, not quality. Sensor size: a SMALLER second number means a BIGGER sensor (1/1.4\" is bigger than 1/1.56\"). Aperture: a SMALLER f-number lets in MORE light (f/1.7 beats f/2.0). Low-light tests in lux: a LOWER number is better, because the phone still takes sharp photos in darker light (2 lux is darker than 4 lux). Optical zoom (a telephoto lens, e.g. 3x optical) stays sharp; 'digital zoom' (e.g. 100x) only crops and enlarges.",
    "storage": "Free space out of the box is what you can actually use. Convert units first: 1 TB is about 1,000 GB, so 0.1 TB is about 100 GB and 0.23 TB about 230 GB; 98,000 MB is about 98 GB. RAM (the first number) does not add storage, and 'virtual RAM' only borrows storage.",
    "price": "Check the price against the budget on your card. A phone above the budget does not meet the buyer's needs even if it is good.",
}


def set_context(set_id):
    s = get_set(set_id)
    labels = catalog()["spec_labels"]
    lines = [f"Buyer: {s['card']['persona']} {s['card']['text']}", "Phones:"]
    for p in s["phones"]:
        specs = "; ".join(f"{labels[k]}: {v}" for k, v in p["specs"].items())
        det = "; ".join(f"{a}: {b}" for a, b in p.get("details", []))
        lines.append(f"* {p['name']} - {specs}. Lab results: {det}. Review: {p['review']}")
    return "\n".join(lines)


def _name(set_id, pid):
    for p in get_set(set_id)["phones"]:
        if p["id"] == pid:
            return p["name"]
    return pid


def build_prompt(set_id, mode, args):
    ctx = set_context(set_id)
    labels = catalog()["spec_labels"]
    if mode == "compare":
        a, b = (args.get("pair") or [None, None])[:2]
        task = (f"Compare {_name(set_id, a)} and {_name(set_id, b)} for this buyer. "
                "Point out which differences matter most for the buyer's priorities and budget, using the lab results.")
    elif mode == "explain":
        spec = args.get("spec") or "battery"
        task = (f"Explain in simple words what the '{labels.get(spec, spec)}' line means and how to compare it fairly "
                "across these phones for this buyer (mention the relevant lab result).")
    elif mode == "ask":
        q = (args.get("question") or "").strip()[:400]
        task = f"Answer the buyer's question: \"{q}\""
    else:
        task = "Give a short overview of the main trade-offs between these phones for this buyer's priorities and budget."
    return f"{ctx}\n\nTask: {task}"


def _version(set_id):
    """Fingerprint of the phone data and the AI instructions: when either changes, old cached answers are not used."""
    return hashlib.sha1((set_context(set_id) + SYSTEM + json.dumps(GLOSSARY, sort_keys=True)).encode("utf-8")).hexdigest()[:8]


def cache_key(set_id, mode, args):
    sid = f"{set_id}@{_version(set_id)}"
    if mode == "ask":
        q = re.sub(r"\s+", " ", (args.get("question") or "").strip().lower())
        return f"{sid}|ask|{q}"[:255]
    if mode == "compare":
        pair = sorted((args.get("pair") or [])[:2])
        return f"{sid}|compare|{','.join(pair)}"
    if mode == "explain":
        return f"{sid}|explain|{args.get('spec') or 'battery'}"
    return f"{sid}|general"


def _clean(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    return text.strip()


def _gemini(prompt):
    if not config.GEMINI_API_KEY:
        raise RuntimeError("no Gemini key")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400},
    }
    r = httpx.post(url, params={"key": config.GEMINI_API_KEY}, json=body, timeout=config.LLM_TIMEOUT_S)
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return _clean("".join(p.get("text", "") for p in parts)), config.GEMINI_MODEL


def _groq(prompt):
    if not config.GROQ_API_KEY:
        raise RuntimeError("no Groq key")
    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        json={"model": config.GROQ_MODEL, "temperature": 0.2, "max_tokens": 700,
              "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]},
        timeout=config.LLM_TIMEOUT_S,
    )
    r.raise_for_status()
    return _clean(r.json()["choices"][0]["message"]["content"]), config.GROQ_MODEL


def fallback_answer(set_id, mode, args):
    s = get_set(set_id)
    labels = catalog()["spec_labels"]
    if mode == "compare":
        pair = (args.get("pair") or [])[:2]
        phones = [p for p in s["phones"] if p["id"] in pair] or s["phones"][:2]
        lines = []
        for p in phones:
            det = ", ".join(f"{a.lower()} {b}" for a, b in p.get("details", [])[:2])
            lines.append(f"- {p['name']}: {p['specs']['price']}; {det}.")
        lines.append(f"- Your card: {s['card']['text']}")
        lines.append("- Compare the lab results for the card's priorities, not only the headline numbers.")
        return "\n".join(lines)
    if mode == "explain":
        spec = args.get("spec") or "battery"
        return f"- {labels.get(spec, spec)}: {GLOSSARY.get(spec, GLOSSARY['battery'])}"
    if mode == "ask":
        return ("- The AI assistant is not available right now.\n"
                "- Open 'Details & review' on each phone: the lab results show real battery life, camera quality and speed.\n"
                f"- Your card: {s['card']['text']}")
    pr = s["card"].get("priorities", [])
    return "\n".join([f"- Your card: {s['card']['text']}"] +
                     [f"- {labels.get(k, k)}: {GLOSSARY.get(k, '')}" for k in pr[:2]])


def answer(set_id, mode, args):
    """Returns dict(text, provider, model, latency_ms, error, cached)."""
    key = cache_key(set_id, mode, args)
    t0 = time.time()
    if os.environ.get("LLM_DISABLED") == "1":      # simulations: do not spend API quota
        return {"text": fallback_answer(set_id, mode, args), "provider": "fallback", "model": None,
                "latency_ms": 0, "error": "LLM disabled", "cached": False}
    with db.engine.connect() as c:
        row = c.execute(select(db.llm_cache.c.response, db.llm_cache.c.provider, db.llm_cache.c.model)
                        .where(db.llm_cache.c.key == key)).first()
    if row:
        return {"text": row[0], "provider": f"cache:{row[1]}", "model": row[2],
                "latency_ms": int((time.time() - t0) * 1000), "error": None, "cached": True}
    prompt = build_prompt(set_id, mode, args)
    errors = []
    for name, fn in (("gemini", _gemini), ("groq", _groq)):
        try:
            text, model = fn(prompt)
            if not text:
                raise RuntimeError("empty answer")
            with db.engine.begin() as c:
                if not c.execute(select(db.llm_cache.c.key).where(db.llm_cache.c.key == key)).first():
                    c.execute(db.llm_cache.insert().values(key=key, response=text, provider=name, model=model,
                                                           created_at=db.now()))
            return {"text": text, "provider": name, "model": model,
                    "latency_ms": int((time.time() - t0) * 1000), "error": "; ".join(errors) or None, "cached": False}
        except Exception as e:  # noqa: BLE001 - any provider failure falls through to the next one
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:160]}")
    return {"text": fallback_answer(set_id, mode, args), "provider": "fallback", "model": None,
            "latency_ms": int((time.time() - t0) * 1000), "error": "; ".join(errors), "cached": False}


def provider_check():
    out = {}
    for name, fn in (("gemini", _gemini), ("groq", _groq)):
        t0 = time.time()
        try:
            text, model = fn("Reply with the single word OK.")
            out[name] = {"ok": True, "model": model, "latency_ms": int((time.time() - t0) * 1000), "sample": text[:40]}
        except Exception as e:  # noqa: BLE001
            out[name] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    return out


def args_json(args):
    return json.dumps(args or {}, sort_keys=True)
