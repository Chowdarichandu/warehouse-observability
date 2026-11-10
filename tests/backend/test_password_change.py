from uuid import uuid4

from fastapi.testclient import TestClient

from obs.api.main import app
from obs.auth import hasher, verify_password
from obs.db import connection


def test_password_change_requires_old_password_and_revokes_other_sessions():
    email = f"password-{uuid4().hex}@example.test"
    with connection() as conn:
        uid = conn.execute(
            "INSERT INTO obs.users(email,display_name,role,password_hash) VALUES(%s,'Password Test','viewer',%s) RETURNING user_id",
            (email, hasher.hash("original password")),
        ).fetchone()["user_id"]
    try:
        with (
            TestClient(app, base_url="https://localhost") as first,
            TestClient(app, base_url="https://localhost") as other,
        ):
            for client in (first, other):
                login = client.post(
                    "/api/auth/login",
                    json={"email": email, "password": "original password"},
                )
                assert login.status_code == 200
                client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            assert (
                first.post(
                    "/api/auth/password",
                    json={
                        "current_password": "wrong",
                        "new_password": "a-new-long-password",
                    },
                ).status_code
                == 403
            )
            changed = first.post(
                "/api/auth/password",
                json={
                    "current_password": "original password",
                    "new_password": "a-new-long-password",
                },
            )
            assert changed.status_code == 200
            assert first.get("/api/me").status_code == 200
            assert other.get("/api/me").status_code == 401
            with connection() as conn:
                assert verify_password(
                    "a-new-long-password",
                    conn.execute(
                        "SELECT password_hash FROM obs.users WHERE user_id=%s", (uid,)
                    ).fetchone()["password_hash"],
                )
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.sessions WHERE user_id=%s", (uid,))
            conn.execute("DELETE FROM obs.users WHERE user_id=%s", (uid,))
