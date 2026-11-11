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
    "metrics_only",
    "trigger_pipelines",
    "manage_tenants",
    "manage_alerts",
    "manage_users",
    "manage_platform",
    "view_module_hrms",
    "view_module_finance",
    "view_module_sap",
    "view_module_pos",
    "view_module_inventory",
    "view_module_support",
    "view_module_hospitality",
]
SYSTEM_ROLE_PERMISSIONS = {
    "admin": [permission for permission in PERMISSIONS if permission != "metrics_only"],
    "operator": ["view_console", "trigger_pipelines", "manage_tenants", "manage_alerts"],
    "viewer": ["view_console"],
}


PERMISSION_MIN_ROLE = {
    "view_console": "viewer",
    "metrics_only": "viewer",
    "trigger_pipelines": "operator",
    "manage_tenants": "operator",
    "manage_alerts": "operator",
    "manage_users": "admin",
    "manage_platform": "admin",
    "view_module_hrms": "viewer",
    "view_module_finance": "viewer",
    "view_module_sap": "viewer",
    "view_module_pos": "viewer",
    "view_module_inventory": "viewer",
    "view_module_support": "viewer",
    "view_module_hospitality": "viewer",
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


def _login_rate_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _prune_login_attempts(key: str, now: float) -> deque[float]:
    attempts = login_attempts[key]
    while attempts and attempts[0] < now - 60:
        attempts.popleft()
    return attempts


def check_login_rate(request: Request, *, record: bool = True) -> None:
    key = _login_rate_key(request)
    now = monotonic()
    attempts = _prune_login_attempts(key, now)
    if len(attempts) >= 10:
        fail(429, "rate_limited", "Too many login attempts. Try again in a minute.")
    if record:
        attempts.append(now)


def record_login_failure(request: Request) -> None:
    key = _login_rate_key(request)
    now = monotonic()
    _prune_login_attempts(key, now).append(now)


def clear_login_attempts(request: Request) -> None:
    login_attempts.pop(_login_rate_key(request), None)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def token(user: dict, csrf: str) -> str:
    sid = str(uuid4())
    issued_at = datetime.now(UTC)
    expires = issued_at + timedelta(days=settings().session_absolute_days)
    with connection() as conn:
        conn.execute(
            "INSERT INTO obs.sessions(id,user_id,expires_at) VALUES(%s,%s,%s)",
            (sid, user["user_id"], expires),
        )
    return jwt.encode(
        {
            "sub": str(user["user_id"]),
            "csrf": csrf,
            "jti": sid,
            "iat": issued_at,
            "exp": expires,
        },
        settings().jwt_secret,
        algorithm="HS256",
    )


def current_user(request: Request) -> dict:
    try:
        claims = jwt.decode(
            request.cookies.get("obs_session", ""), settings().jwt_secret, algorithms=["HS256"]
        )
        # Check account status and both session bounds together. last_seen_at
        # is refreshed only after this gate succeeds, so stale clients cannot
        # keep an idle session alive by sending requests.
        with connection() as conn:
            user = conn.execute(
                """
                SELECT u.user_id,u.email,u.display_name,u.role,u.role_name
                FROM obs.users u
                JOIN obs.sessions s USING(user_id)
                WHERE u.user_id=%s
                  AND u.status='active'
                  AND s.id=%s
                  AND s.revoked_at IS NULL
                  AND s.expires_at>now()
                  AND s.created_at > now() - (%s * interval '1 day')
                  AND s.last_seen_at > now() - (%s * interval '1 hour')
                """,
                (
                    int(claims["sub"]),
                    claims["jti"],
                    settings().session_absolute_days,
                    settings().session_idle_hours,
                ),
            ).fetchone()
            if user:
                conn.execute(
                    "UPDATE obs.sessions SET last_seen_at=now() WHERE id=%s",
                    (claims["jti"],),
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
    if "metrics_only" in granted and not _metrics_only_request_allowed(request):
        fail(
            403,
            "metrics_only",
            "This account is limited to workspace metrics and account settings.",
        )
    return {
        **user,
        "csrf_token": claims["csrf"],
        "session_id": claims["jti"],
        "permissions": granted,
    }


def _metrics_only_request_allowed(request: Request) -> bool:
    """Allow a metrics-only identity to use the dashboard and manage its own session."""
    path = request.url.path
    if request.method in {"GET", "HEAD"}:
        return path in {
            "/api/me",
            "/api/access",
            "/api/metrics/overview",
            "/api/metrics/tenants",
            "/api/stream",
        } or (
            len(path.split("/")) == 5
            and path.split("/")[1:3] == ["api", "tenants"]
            and bool(path.split("/")[3])
            and path.split("/")[4] == "metrics"
        )
    return request.method == "POST" and path in {
        "/api/auth/logout",
        "/api/auth/password",
        "/api/auth/change-password",
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
