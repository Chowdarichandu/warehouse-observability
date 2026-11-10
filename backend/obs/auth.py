import secrets
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from time import monotonic
from urllib.parse import urlsplit
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request

from obs.db import connection, one
from obs.settings import settings

hasher = PasswordHasher()
login_attempts: dict[str, deque[float]] = defaultdict(deque)

# Permission catalog. System roles map to fixed bundles; a custom role
# (obs.roles) assigned via role_name replaces the bundle for its user.
PERMISSIONS = [
    "view_console",
    "trigger_pipelines",
    "manage_tenants",
    "manage_alerts",
    "manage_users",
    "manage_platform",
]
SYSTEM_ROLE_PERMISSIONS = {
    "admin": list(PERMISSIONS),
    "operator": ["view_console", "trigger_pipelines", "manage_tenants", "manage_alerts"],
    "viewer": ["view_console"],
}


def user_permissions(user: dict) -> list:
    """Effective permission bundle for a user row (role + optional role_name)."""
    role_name = user.get("role_name")
    if role_name:
        row = one("SELECT permissions FROM obs.roles WHERE name=%s", (role_name,))
        if row and isinstance(row.get("permissions"), list):
            return [p for p in row["permissions"] if p in PERMISSIONS]
    return list(SYSTEM_ROLE_PERMISSIONS.get(user.get("role") or "viewer", ["view_console"]))


def require_permission(permission: str) -> Callable[..., dict]:
    def dependency(user: dict = Depends(current_user)) -> dict:
        if permission not in user.get("permissions", []):
            fail(403, "forbidden", "Your role does not allow this action.")
        return user

    return dependency


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
    sid = str(uuid4())
    expires = datetime.now(UTC) + timedelta(hours=settings().session_hours)
    with connection() as conn:
        conn.execute(
            "INSERT INTO obs.sessions(id,user_id,expires_at) VALUES(%s,%s,%s)",
            (sid, user["user_id"], expires),
        )
    return jwt.encode(
        {"sub": str(user["user_id"]), "csrf": csrf, "jti": sid, "exp": expires},
        settings().jwt_secret,
        algorithm="HS256",
    )


def current_user(request: Request) -> dict:
    try:
        claims = jwt.decode(
            request.cookies.get("obs_session", ""), settings().jwt_secret, algorithms=["HS256"]
        )
        user = one(
            "SELECT u.user_id,u.email,u.display_name,u.role,u.role_name FROM obs.users u JOIN obs.sessions s USING(user_id) WHERE u.user_id=%s AND s.id=%s AND s.revoked_at IS NULL AND s.expires_at>now()",
            (int(claims["sub"]), claims["jti"]),
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
        allowed_hosts = {request.headers.get("host"), urlsplit(settings().console_url).netloc}
        if origin and urlsplit(origin).netloc not in allowed_hosts:
            fail(403, "csrf_origin", "Cross-origin action blocked.")
    return {
        **user,
        "csrf_token": claims["csrf"],
        "session_id": claims["jti"],
        "permissions": user_permissions(user),
    }


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
