"""Researcher login: one password (ADMIN_PASSWORD), a signed cookie that lasts 12 hours."""
import hashlib
import hmac
import time

from fastapi import HTTPException, Request

from . import config

COOKIE = "hti_admin"
TTL_S = 12 * 3600


def _sign(exp: int) -> str:
    return hmac.new(config.SECRET_KEY.encode(), f"admin|{exp}".encode(), hashlib.sha256).hexdigest()


def make_token() -> str:
    exp = int(time.time()) + TTL_S
    return f"{exp}.{_sign(exp)}"


def check_password(pw: str) -> bool:
    if not config.ADMIN_PASSWORD:
        return False
    return hmac.compare_digest(pw.encode(), config.ADMIN_PASSWORD.encode())


def require_admin(request: Request):
    tok = request.cookies.get(COOKIE, "")
    try:
        exp_s, sig = tok.split(".", 1)
        exp = int(exp_s)
    except ValueError:
        raise HTTPException(401, "Researcher login required")
    if exp < time.time() or not hmac.compare_digest(sig, _sign(exp)):
        raise HTTPException(401, "Researcher login required")
    return True
