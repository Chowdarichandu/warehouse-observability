from contextlib import contextmanager
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from obs import auth
from obs import oidc
from obs.api.routers import auth as auth_router
from obs.api.schemas import Login


def request_with_cookie(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/me",
            "headers": [(b"cookie", f"obs_session={token}".encode())],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("localhost", 443),
        }
    )


def post_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": [(b"host", b"localhost")],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("localhost", 80),
        }
    )


class Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, row):
        self.row = row
        self.statements: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.statements.append((sql, tuple(params or ())))
        return Cursor(self.row)


def patch_auth(monkeypatch, connection, claims):
    config = SimpleNamespace(
        jwt_secret="session-test-secret",
        console_url="https://localhost",
        session_idle_hours=12,
        session_absolute_days=7,
        auth_provider="oidc",
    )
    monkeypatch.setattr(auth, "settings", lambda: config)
    monkeypatch.setattr(auth.jwt, "decode", lambda *args, **kwargs: claims)
    monkeypatch.setattr(auth, "user_permissions", lambda user: ["view_console"])

    @contextmanager
    def connection_context():
        yield connection

    monkeypatch.setattr(auth, "connection", connection_context)


def test_current_user_refreshes_last_seen_for_active_session(monkeypatch):
    row = {"user_id": 7, "email": "active@example.com", "role": "viewer"}
    connection = Connection(row)
    patch_auth(
        monkeypatch, connection, {"sub": "7", "jti": "session-1", "csrf": "csrf"}
    )

    user = auth.current_user(request_with_cookie("signed"))

    assert user["user_id"] == 7
    assert any(
        "UPDATE obs.sessions SET last_seen_at=now()" in sql and params == ("session-1",)
        for sql, params in connection.statements
    )
    query = connection.statements[0][0]
    assert "u.status='active'" in query
    assert "s.created_at > now()" in query
    assert "s.last_seen_at > now()" in query


@pytest.mark.parametrize("reason", ["disabled", "idle", "absolute"])
def test_current_user_rejects_sessions_that_fail_policy(monkeypatch, reason):
    connection = Connection(None)
    patch_auth(
        monkeypatch,
        connection,
        {"sub": "7", "jti": f"{reason}-session", "csrf": "csrf"},
    )

    with pytest.raises(HTTPException) as error:
        auth.current_user(request_with_cookie("signed"))

    assert error.value.status_code == 401
    assert error.value.detail["code"] == "unauthenticated"


def test_token_has_seven_day_absolute_expiry(monkeypatch):
    connection = Connection(None)
    config = SimpleNamespace(
        jwt_secret="session-test-secret",
        session_idle_hours=12,
        session_absolute_days=7,
    )
    monkeypatch.setattr(auth, "settings", lambda: config)

    @contextmanager
    def connection_context():
        yield connection

    monkeypatch.setattr(auth, "connection", connection_context)
    encoded = auth.token({"user_id": 7}, "csrf")
    claims = jwt.decode(encoded, config.jwt_secret, algorithms=["HS256"])

    assert claims["sub"] == "7"
    assert 6.9 * 86400 < claims["exp"] - claims["iat"] < 7.1 * 86400


def test_local_login_rejects_disabled_account_without_cookie(monkeypatch):
    config = SimpleNamespace(
        auth_provider="local",
        mode="demo",
        console_url="http://localhost",
        cookie_secure=False,
        session_absolute_days=7,
    )
    disabled = {
        "user_id": 7,
        "email": "disabled@example.com",
        "status": "disabled",
        "password_hash": "encoded",
    }
    monkeypatch.setattr(auth_router, "settings", lambda: config)
    monkeypatch.setattr(auth_router, "one", lambda *args: disabled)
    monkeypatch.setattr(auth_router, "verify_password", lambda *args: True)
    monkeypatch.setattr(auth_router, "record_login_failure", lambda request: None)
    monkeypatch.setattr(auth_router, "clear_login_attempts", lambda request: None)
    monkeypatch.setattr(
        auth_router,
        "token",
        lambda *args: pytest.fail("disabled login must not create a session token"),
    )

    from starlette.responses import Response

    response = Response()
    with pytest.raises(HTTPException) as error:
        auth_router.login(
            Login(email="disabled@example.com", password="correct"),
            post_request(),
            response,
        )

    assert error.value.status_code == 401
    assert error.value.detail["code"] == "invalid_credentials"
    assert "obs_session" not in response.headers.get("set-cookie", "")


def test_oidc_identity_rejects_disabled_account_before_session_creation(monkeypatch):
    config = SimpleNamespace(
        oidc_groups_claim="groups",
        oidc_group_roles={"console-viewers": "viewer"},
    )
    connection = Connection(
        {"user_id": 9, "email": "disabled@example.com", "status": "disabled"}
    )
    monkeypatch.setattr(oidc, "settings", lambda: config)

    @contextmanager
    def connection_context():
        yield connection

    monkeypatch.setattr(oidc, "connection", connection_context)

    with pytest.raises(HTTPException) as error:
        oidc.identity(
            {
                "email": "disabled@example.com",
                "email_verified": True,
                "groups": ["console-viewers"],
                "iss": "https://issuer.example",
                "sub": "subject-9",
            }
        )

    assert error.value.status_code == 401
    assert error.value.detail["code"] == "authentication_failed"
    assert not any("UPDATE obs.users" in sql for sql, _ in connection.statements)
