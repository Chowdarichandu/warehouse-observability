import secrets
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from time import monotonic
from urllib.parse import urlsplit

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request

from obs.db import one
from obs.settings import settings

hasher = PasswordHasher()
login_attempts: dict[str, deque[float]] = defaultdict(deque)


def fail(status: int, code: str, message: str) -> None:
    raise HTTPException(status, detail={"code": code, "message": message})


def check_login_rate(request: Request) -> None:
    key = request.client.host if request.client else "unknown"
    attempts = login_attempts[key]
    now = monotonic()
    while attempts and attempts[0] < now - 60:
        attempts.popleft()
    if len(attempts) >= 10:
        fail(429, "rate_limited", "Too many login attempts. Try again in a minute.")
    attempts.append(now)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def token(user: dict, csrf: str) -> str:
    return jwt.encode(
        {"sub": str(user["user_id"]), "csrf": csrf, "exp": datetime.now(UTC) + timedelta(hours=12)},
        settings().jwt_secret,
        algorithm="HS256",
    )


def current_user(request: Request) -> dict:
    try:
        claims = jwt.decode(
            request.cookies.get("obs_session", ""), settings().jwt_secret, algorithms=["HS256"]
        )
        user = one(
            "SELECT user_id,email,display_name,role FROM obs.users WHERE user_id=%s",
            (int(claims["sub"]),),
        )
        if not user:
            fail(401, "unauthenticated", "Please sign in.")
    except (jwt.InvalidTokenError, ValueError, KeyError):
        fail(401, "unauthenticated", "Please sign in.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not secrets.compare_digest(sent, claims.get("csrf", "")):
            fail(403, "csrf", "Invalid CSRF token. Refresh the page and try again.")
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            fail(403, "csrf_origin", "Cross-origin action blocked.")
    return {**user, "csrf_token": claims["csrf"]}


def require_role(role: str) -> Callable[..., dict]:
    def dependency(user: dict = Depends(current_user)) -> dict:
        if {"viewer": 0, "operator": 1, "admin": 2}[user["role"]] < {
            "viewer": 0,
            "operator": 1,
            "admin": 2,
        }[role]:
            fail(403, "forbidden", f"This action requires the {role} role.")
        return user

    return dependency
