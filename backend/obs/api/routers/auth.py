import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response

from obs import oidc
from obs.api.schemas import ChangePassword, Login, Message, User
from obs.audit import audit
from obs.auth import check_login_rate, current_user, fail, hasher, token, verify_password
from obs.db import connection, one
from obs.settings import settings

router = APIRouter(tags=["Authentication"])
DUMMY_HASH = hasher.hash("invalid-user-timing-padding")


@router.post("/auth/login", response_model=User)
def login(data: Login, request: Request, response: Response) -> dict:
    if settings().auth_provider != "local" or settings().mode != "demo":
        fail(403, "sso_required", "Use your organization account to sign in.")
    check_login_rate(request)
    origin = request.headers.get("origin")
    allowed_hosts = {request.headers.get("host"), urlsplit(settings().console_url).netloc}
    if origin and urlsplit(origin).netloc not in allowed_hosts:
        fail(403, "csrf_origin", "Cross-origin login blocked.")
    user = one("SELECT * FROM obs.users WHERE email=%s", (data.email.lower().strip(),))
    valid = verify_password(data.password, user.get("password_hash") or DUMMY_HASH)
    if not user or not valid:
        fail(401, "invalid_credentials", "Email or password is incorrect.")
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        "obs_session",
        token(user, csrf),
        max_age=43200,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="lax",
        path="/api",
    )
    with connection() as conn:
        audit(conn, user["email"], "login", str(user["user_id"]))
    return {**user, "csrf_token": csrf}


@router.post("/auth/change-password", response_model=Message)
def change_password(
    data: ChangePassword, user: dict = Depends(current_user)
) -> dict:
    if settings().auth_provider != "local":
        fail(403, "sso_required", "Use your organization account to manage your password.")
    row = one("SELECT * FROM obs.users WHERE user_id=%s", (user["user_id"],))
    valid = verify_password(data.current_password, row.get("password_hash") or DUMMY_HASH)
    if not row or not valid:
        fail(401, "invalid_credentials", "Current password is incorrect.")
    if len(data.new_password) < 8:
        fail(422, "weak_password", "New password must be at least 8 characters.")
    if data.new_password == data.current_password:
        fail(422, "password_reused", "New password must differ from the current password.")
    with connection() as conn:
        conn.execute(
            "UPDATE obs.users SET password_hash=%s WHERE user_id=%s",
            (hasher.hash(data.new_password), user["user_id"]),
        )
        audit(conn, user["email"], "change_password", str(user["user_id"]))
    return {"message": "Password changed.", "simulated": False}


@router.post("/auth/logout", response_model=Message)
def logout(response: Response, user: dict = Depends(current_user)) -> dict:
    response.delete_cookie(
        "obs_session", path="/api", secure=settings().cookie_secure, httponly=True, samesite="lax"
    )
    with connection() as conn:
        conn.execute("UPDATE obs.sessions SET revoked_at=now() WHERE id=%s", (user["session_id"],))
        audit(conn, user["email"], "logout")
    return {"message": "Signed out.", "simulated": False}


@router.get("/me", response_model=User)
def me(user: dict = Depends(current_user)) -> dict:
    return user


@router.get("/auth/oidc/start")
def oidc_start() -> Response:
    return oidc.start()


@router.get("/auth/oidc/callback")
def oidc_callback(request: Request, code: str = "", state: str = "") -> Response:
    return oidc.callback(request, code, state)
