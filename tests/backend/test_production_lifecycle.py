from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from obs import oidc
from obs.actions import live as operations
from obs.alerter import notify
from obs.api.main import app
from obs.db import connection, one
from obs.integrations.http import UpstreamError
from obs.settings import settings


@pytest.fixture
def live(monkeypatch):
    config = settings()
    monkeypatch.setattr("obs.api.main.assert_no_demo_users", lambda: None)
    for key, value in {
        "mode": "live",
        "live_actions_enabled": True,
        "console_url": "https://localhost",
        "oidc_issuer": "https://id.example.test",
        "oidc_client_id": "console",
        "oidc_group_roles": {
            "readers": "viewer",
            "operators": "operator",
            "admins": "admin",
        },
    }.items():
        monkeypatch.setattr(config, key, value)
    return config


def test_oidc_explicit_group_mapping_and_identity_binding(live):
    subject = str(uuid4())
    claims = {
        "iss": live.oidc_issuer,
        "sub": subject,
        "email": f"{subject}@example.test",
        "email_verified": True,
        "groups": ["readers", "operators"],
    }
    try:
        user = oidc.identity(claims)
        assert user["role"] == "operator"
        assert oidc.identity(claims | {"groups": ["readers"]})["role"] == "viewer"
        for change in [
            {"groups": []},
            {"groups": "admins"},
            {"email_verified": False},
            {"sub": "different-subject"},
        ]:
            with pytest.raises(HTTPException) as error:
                oidc.identity(claims | change)
            assert error.value.status_code == 403
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.oidc_identities WHERE subject=%s", (subject,))
            conn.execute("DELETE FROM obs.users WHERE email=%s", (claims["email"],))


def test_oidc_callback_rejects_replay_and_bad_signature(live, monkeypatch):
    monkeypatch.setattr(live, "auth_provider", "oidc")
    metadata = {
        "issuer": live.oidc_issuer,
        "authorization_endpoint": live.oidc_issuer + "/authorize",
        "token_endpoint": live.oidc_issuer + "/token",
        "jwks_uri": live.oidc_issuer + "/keys",
    }

    def upstream(method, url, **kwargs):
        if url.endswith("openid-configuration"):
            return metadata
        if url.endswith("/token"):
            return {"id_token": "invalid-token"}
        return {"keys": []}

    monkeypatch.setattr(oidc, "upstream", upstream)
    client = TestClient(app, base_url="https://localhost", follow_redirects=False)
    response = client.get("/api/auth/oidc/start")
    assert (
        response.status_code == 302
        and "code_challenge=" in response.headers["location"]
    )
    state = client.cookies.get("obs_oidc_state")
    failed = client.get(
        "/api/auth/oidc/callback", params={"state": state, "code": "code"}
    )
    assert failed.status_code == 401
    assert (
        client.get(
            "/api/auth/oidc/callback", params={"state": state, "code": "code"}
        ).status_code
        == 400
    )
    assert (
        client.get(
            "/api/auth/oidc/callback", params={"state": "mismatch", "code": "code"}
        ).status_code
        == 400
    )
    client.close()


def test_logout_invalidates_a_copied_session():
    client = TestClient(app, base_url="https://localhost")
    response = client.post(
        "/api/auth/login",
        json={"email": "viewer@demo.local", "password": settings().demo_password},
    )
    assert response.status_code == 200
    copied = client.cookies.get("obs_session")
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set("obs_session", copied, domain="localhost.local", path="/api")
    assert client.get("/api/me").status_code == 401
    client.close()


def test_durable_operations_do_not_repeat_ambiguous_write(live, monkeypatch):
    key = "test-operation:" + str(uuid4())
    calls = []

    class Airflow:
        def __init__(self, **kwargs):
            pass

        def retry(self, payload):
            calls.append(payload)
            raise UpstreamError(503, ambiguous=True)

    monkeypatch.setattr(operations, "Airflow", Airflow)
    try:
        with pytest.raises(HTTPException) as first:
            operations.execute(
                "retry", "test-run", "operator", {"dag_id": "mysql_cdc"}, key
            )
        assert first.value.status_code == 502
        assert (
            one("SELECT status FROM obs.operations WHERE idempotency_key=%s", (key,))[
                "status"
            ]
            == "uncertain"
        )
        with pytest.raises(HTTPException) as second:
            operations.execute(
                "retry", "test-run", "operator", {"dag_id": "mysql_cdc"}, key
            )
        assert second.value.status_code == 409 and len(calls) == 1
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.operations WHERE idempotency_key=%s", (key,))


def test_notification_outbox_retries_and_observes_failure(live, monkeypatch):
    channel = "test-" + str(uuid4())
    with connection() as conn:
        conn.execute(
            "INSERT INTO obs.notification_channels(channel_id,kind,target_env) VALUES(%s,'slack','TEST_WEBHOOK')",
            (channel,),
        )
        conn.execute(
            "INSERT INTO obs.notification_deliveries(channel_id,kind,status,message) VALUES(%s,'test','pending','Test')",
            (channel,),
        )

    def broken(item):
        if item["channel_id"] == channel:
            raise RuntimeError("https://hooks.slack.com/services/private-secret")

    monkeypatch.setattr(notify, "send", broken)
    try:
        notify.dispatch(limit=1)
        delivery = one(
            "SELECT * FROM obs.notification_deliveries WHERE channel_id=%s", (channel,)
        )
        assert delivery["status"] == "pending" and delivery["attempts"] == 1
        assert delivery["next_attempt_at"] > datetime.now(UTC)
        assert "private-secret" not in delivery["last_error"]
        with connection() as conn:
            conn.execute(
                "UPDATE obs.notification_deliveries SET next_attempt_at=now(),attempts=%s WHERE id=%s",
                (live.notification_max_attempts - 1, delivery["id"]),
            )
        notify.dispatch(limit=1)
        assert (
            one(
                "SELECT status FROM obs.notification_deliveries WHERE id=%s",
                (delivery["id"],),
            )["status"]
            == "failed"
        )
    finally:
        with connection() as conn:
            conn.execute(
                "DELETE FROM obs.notification_deliveries WHERE channel_id=%s",
                (channel,),
            )
            conn.execute(
                "DELETE FROM obs.notification_channels WHERE channel_id=%s", (channel,)
            )


def test_successful_operation_is_idempotent(live, monkeypatch):
    key = "test-operation:" + str(uuid4())
    calls = []

    class Airbyte:
        def __init__(self, **kwargs):
            pass

        def sync(self, connection_id):
            calls.append(connection_id)
            return {"jobId": 777}

    monkeypatch.setattr(operations, "Airbyte", Airbyte)
    try:
        first = operations.execute(
            "retry",
            "test-run",
            "operator",
            {"airbyte_connection_id": "connection"},
            key,
        )
        second = operations.execute(
            "retry",
            "test-run",
            "operator",
            {"airbyte_connection_id": "connection"},
            key,
        )
        assert first["id"] == second["id"] and second["status"] == "succeeded"
        assert calls == ["connection"]
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.operations WHERE idempotency_key=%s", (key,))


def test_oidc_signed_login_and_session_roundtrip(live, monkeypatch):
    import json
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    monkeypatch.setattr(live, "auth_provider", "oidc")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key())) | {
        "kid": "test-key",
        "use": "sig",
        "alg": "RS256",
    }
    subject = str(uuid4())
    nonce = ""

    def upstream(method, url, **kwargs):
        if url.endswith("openid-configuration"):
            return {
                "issuer": live.oidc_issuer,
                "authorization_endpoint": live.oidc_issuer + "/authorize",
                "token_endpoint": live.oidc_issuer + "/token",
                "jwks_uri": live.oidc_issuer + "/keys",
            }
        if url.endswith("/keys"):
            return {"keys": [public]}
        assert kwargs["data"]["code_verifier"]
        claims = {
            "iss": live.oidc_issuer,
            "sub": subject,
            "aud": live.oidc_client_id,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "nonce": nonce,
            "email": subject + "@example.test",
            "email_verified": True,
            "groups": ["admins"],
        }
        return {
            "id_token": jwt.encode(
                claims, private, algorithm="RS256", headers={"kid": "test-key"}
            )
        }

    monkeypatch.setattr(oidc, "upstream", upstream)
    client = TestClient(app, base_url="https://localhost", follow_redirects=False)
    try:
        assert client.get("/api/auth/oidc/start").status_code == 302
        state = client.cookies.get("obs_oidc_state")
        import hashlib

        nonce = one(
            "SELECT nonce FROM obs.oidc_states WHERE state_hash=%s",
            (hashlib.sha256(state.encode()).hexdigest(),),
        )["nonce"]
        response = client.get(
            "/api/auth/oidc/callback",
            params={"state": state, "code": "authorization-code"},
        )
        assert response.status_code == 302 and response.headers["location"] == "/"
        session = client.get("/api/me")
        assert session.status_code == 200 and session.json()["role"] == "admin"
        assert session.json()["csrf_token"]
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "admin@demo.local", "password": "demo"},
            ).status_code
            == 403
        )
    finally:
        client.close()
        with connection() as conn:
            user = conn.execute(
                "SELECT user_id FROM obs.oidc_identities WHERE subject=%s", (subject,)
            ).fetchone()
            if user:
                conn.execute(
                    "DELETE FROM obs.sessions WHERE user_id=%s", (user["user_id"],)
                )
                conn.execute(
                    "DELETE FROM obs.oidc_identities WHERE subject=%s", (subject,)
                )
                conn.execute(
                    "DELETE FROM obs.users WHERE user_id=%s", (user["user_id"],)
                )
