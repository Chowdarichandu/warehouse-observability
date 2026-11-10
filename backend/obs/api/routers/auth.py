import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from obs import oidc
from obs.api.schemas import (
    ForgotPasswordIn,
    ForgotPasswordResult,
    Login,
    Message,
    User,
)
from obs.audit import audit
from obs.auth import (
    check_login_rate,
    current_user,
    fail,
    hasher,
    token,
    user_permissions,
    verify_password,
)
from obs.db import connection, one
from obs.settings import settings

router = APIRouter(tags=["Authentication"])
DUMMY_HASH = hasher.hash("invalid-user-timing-padding")


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


@router.post("/auth/password", response_model=Message)
@router.post("/auth/change-password", response_model=Message)
def change_password(
    data: PasswordChange, request: Request, user: dict = Depends(current_user)
) -> dict:
    if settings().auth_provider != "local" or settings().mode != "demo":
        fail(403, "sso_managed", "Change your password through your identity provider.")
    check_login_rate(request)
    with connection() as conn:
        account = conn.execute(
            "SELECT password_hash FROM obs.users WHERE user_id=%s FOR UPDATE", (user["user_id"],)
        ).fetchone()
        if not account or not verify_password(
            data.current_password, account["password_hash"] or DUMMY_HASH
        ):
            fail(403, "invalid_credentials", "Current password is incorrect.")
        if data.current_password == data.new_password:
            fail(422, "password_reused", "New password must differ from the current password.")
        conn.execute(
            "UPDATE obs.users SET password_hash=%s WHERE user_id=%s",
            (hasher.hash(data.new_password), user["user_id"]),
        )
        conn.execute(
            "UPDATE obs.sessions SET revoked_at=now() WHERE user_id=%s AND id<>%s",
            (user["user_id"], user["session_id"]),
        )
        audit(conn, user["email"], "change_password", str(user["user_id"]))
    return {"message": "Password updated. Other sessions have been signed out.", "simulated": False}


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
    valid = verify_password(data.password, (user or {}).get("password_hash") or DUMMY_HASH)
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
    return {**user, "csrf_token": csrf, "permissions": user_permissions(user)}


@router.post("/auth/forgot-password", response_model=ForgotPasswordResult)
def forgot_password(data: ForgotPasswordIn, request: Request) -> dict:
    check_login_rate(request)
    if (
        settings().mode != "demo"
        or settings().auth_provider != "local"
        or not settings().demo_unsafe_self_service_password_reset
    ):
        # Never reveal whether the account exists; real resets go through an
        # administrator or the identity provider.
        return {
            "message": "If this account exists, an administrator can reset its password from Administration → Users & roles.",
            "temporary_password": None,
        }
    row = one("SELECT * FROM obs.users WHERE email=%s", (data.email.lower().strip(),))
    if not row or not row.get("password_hash"):
        return {
            "message": "No local account uses that email in this demo workspace.",
            "temporary_password": None,
        }
    import secrets as _secrets

    temporary = "Pravah-" + _secrets.token_urlsafe(9)
    with connection() as conn:
        conn.execute(
            "UPDATE obs.users SET password_hash=%s WHERE user_id=%s",
            (hasher.hash(temporary), row["user_id"]),
        )
        conn.execute(
            "UPDATE obs.sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL",
            (row["user_id"],),
        )
        audit(conn, row["email"], "forgot_password_reset", str(row["user_id"]))
    return {
        "message": "Demo workspace: use this temporary password to sign in, then change it from your profile menu.",
        "temporary_password": temporary,
    }


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
