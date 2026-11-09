import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response

from obs import oidc
from obs.api.schemas import Login, Message, User
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
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
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
