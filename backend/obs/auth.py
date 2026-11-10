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

from obs.access import ROLE_RANK, role_at_least
from obs.db import connection, one
from obs.settings import settings

hasher = PasswordHasher()
login_attempts: dict[str, deque[float]] = defaultdict(deque)


def temporary_password() -> str:
    """One-time password shown once to an admin. Letters and digits only, so
    it never renders with a doubled or leading dash."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "Pravah-" + "".join(secrets.choice(alphabet) for _ in range(10))


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


PERMISSION_MIN_ROLE = {
    "view_console": "viewer",
    "trigger_pipelines": "operator",
    "manage_tenants": "operator",
    "manage_alerts": "operator",
    "manage_users": "admin",
    "manage_platform": "admin",
}


def effective_permissions(role: str, bundle: list[str]) -> set[str]:
    return {
        p
        for p in bundle
        if p in PERMISSION_MIN_ROLE and role_at_least(role, PERMISSION_MIN_ROLE[p])
    }


def user_permissions(user: dict) -> list:
    """Effective permission bundle for a user row: the role (or custom role)
    bundle, adjusted by the user's individual grants and revokes."""
    role_name = user.get("role_name")
    if role_name and settings().auth_provider != "oidc":
        row = one("SELECT permissions FROM obs.roles WHERE name=%s", (role_name,))
        bundle = (
            [p for p in row["permissions"] if p in PERMISSIONS]
            if row and isinstance(row.get("permissions"), list)
            else []
        )
    else:
        bundle = list(SYSTEM_ROLE_PERMISSIONS.get(user.get("role"), []))
    user_id = user.get("user_id")
    if user_id and settings().auth_provider != "oidc":
        row = one(
            "SELECT grants, revokes FROM obs.user_permission_overrides WHERE user_id=%s",
            (user_id,),
        )
        if row:
            revokes = {p for p in (row.get("revokes") or []) if p in PERMISSIONS}
            grants = [p for p in (row.get("grants") or []) if p in PERMISSIONS]
            bundle = [p for p in bundle if p not in revokes]
            bundle += [p for p in grants if p not in bundle]
    return bundle


def require_permission(permission: str) -> Callable[..., dict]:
    def dependency(user: dict = Depends(current_user)) -> dict:
        minimum = PERMISSION_MIN_ROLE.get(permission)
        if (
            not minimum
            or not role_at_least(user.get("role", ""), minimum)
            or permission not in user.get("permissions", [])
        ):
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
    granted = user_permissions(user)
    if "view_console" not in granted:
        fail(403, "forbidden", "Your assigned role cannot access this workspace.")
    return {
        **user,
        "csrf_token": claims["csrf"],
        "session_id": claims["jti"],
        "permissions": granted,
    }


def require_role(role: str, permission: str = "view_console") -> Callable[..., dict]:
    if role not in ROLE_RANK:
        raise ValueError("Unknown required workspace role")

    def dependency(user: dict = Depends(current_user)) -> dict:
        if not role_at_least(user.get("role", ""), role):
            fail(403, "forbidden", f"This action requires the {role} role.")
        if permission not in user.get("permissions", []):
            fail(403, "forbidden", "Your assigned role does not grant this permission.")
        return user

    return dependency
