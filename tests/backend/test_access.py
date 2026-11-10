from contextlib import contextmanager

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from obs.access import CAPABILITIES, permissions, role_at_least
from obs.api.main import app
from obs.api.routers import actions
from obs.auth import require_role
from obs.db import connection, one
from obs.settings import settings


def test_access_requires_authentication():
    with TestClient(app, base_url="https://localhost") as client:
        assert client.get("/api/access").status_code == 401


@pytest.mark.parametrize("role", ["viewer", "operator", "admin"])
def test_access_policy_describes_effective_role_without_secrets(clients, role):
    response = clients[role].get("/api/access")
    assert response.status_code == 200
    result = response.json()
    assert (
        result["role"] == role and result["identity"]["email"] == f"{role}@demo.local"
    )
    assert result["policy_source"] == "workspace_roles"
    assert result["role_assignment_managed"] is False
    assert "workspace.read" in result["capabilities"]
    assert len(result["permissions"]) == len(CAPABILITIES)
    assert {item["role"] for item in result["roles"]} == {"viewer", "operator", "admin"}
    assert ("pipelines.retry" in result["capabilities"]) == (role != "viewer")
    assert ("access.revoke_sessions" in result["capabilities"]) == (role == "admin")
    assert "csrf" not in response.text and "oidc_issuer" not in response.text
    assert "password" not in response.text and "secret" not in response.text


def test_canonical_role_checks_fail_closed():
    assert role_at_least("admin", "viewer") and role_at_least("operator", "operator")
    assert not role_at_least("viewer", "operator")
    assert not role_at_least("Administrator", "viewer")
    with pytest.raises(HTTPException) as denied:
        require_role("operator")({"role": "future_untrusted_role"})
    assert denied.value.status_code == 403
    with pytest.raises(ValueError):
        require_role("external_superuser")


def test_live_disabled_actions_are_distinct_from_role_grants(monkeypatch):
    config = settings()
    monkeypatch.setattr(config, "mode", "live")
    monkeypatch.setattr(config, "live_actions_enabled", False)
    policy = {item["id"]: item for item in permissions("admin", config)}
    assert (
        policy["pipelines.retry"]["allowed"]
        and not policy["pipelines.retry"]["enabled"]
    )
    assert "Live actions" in policy["pipelines.retry"]["reason"]
    assert policy["workspace.read"]["enabled"] and policy["alerts.respond"]["enabled"]
    monkeypatch.setattr(config, "live_actions_enabled", True)
    monkeypatch.setattr(config, "registry_dags_enabled", False)
    monkeypatch.setattr(config, "quality_enabled", False)
    policy = {item["id"]: item for item in permissions("operator", config)}
    assert policy["pipelines.retry"]["enabled"]
    assert not policy["onboarding.start"]["enabled"]
    assert not policy["quality.run"]["enabled"]
    assert not policy["quality.configure"]["allowed"]


def test_oidc_roles_are_managed_and_direct_role_edit_is_forbidden(clients, monkeypatch):
    monkeypatch.setattr(settings(), "auth_provider", "oidc")
    result = clients["admin"].get("/api/access").json()
    assert result["identity"]["provider"] == "oidc"
    assert result["policy_source"] == "oidc_group_mapping"
    assert result["role_assignment_managed"]
    assert "access.assign_roles" not in result["capabilities"]
    assert "access.assign_roles" in result["role_capabilities"]
    assert "access.revoke_sessions" in result["capabilities"]
    response = clients["admin"].patch("/api/users/0", json={"role": "admin"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "sso_managed_roles"


@pytest.mark.parametrize("role", ["viewer", "operator"])
@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("patch", "/api/tenants/access_fixture", {"status": "paused"}),
        ("patch", "/api/users/0", {"role": "admin"}),
        ("post", "/api/users/0/revoke-sessions", None),
        ("post", "/api/channels/access_fixture/test", None),
        ("patch", "/api/quality/checks/0", {"enabled": True}),
    ],
)
def test_non_admin_cannot_call_admin_mutations(clients, role, method, path, payload):
    assert clients[role].request(method, path, json=payload).status_code == 403


def test_viewer_cannot_retry_onboard_or_run_quality_checks(clients):
    for path, payload in [
        ("/api/runs/access_fixture/retry", None),
        (
            "/api/onboarding",
            {"tenant_id": "access_fixture", "display_name": "Access fixture"},
        ),
        ("/api/quality/checks/0/run", None),
    ]:
        assert clients["viewer"].post(path, json=payload).status_code == 403


def test_operator_retry_and_onboarding_reach_services_without_admin_role(
    clients, monkeypatch
):
    called = []

    def retry(key, actor):
        called.append(("retry", actor))
        return {"run_key": key, "message": "Permission fixture", "simulated": True}

    def onboard(data, actor):
        called.append(("onboard", actor))
        return {"tenant_id": data.tenant_id, "status": "onboarding", "events": []}

    monkeypatch.setattr(actions, "retry_action", retry)
    monkeypatch.setattr(actions, "start", onboard)
    assert clients["operator"].post("/api/runs/access_fixture/retry").status_code == 200
    assert (
        clients["operator"]
        .post(
            "/api/onboarding",
            json={"tenant_id": "access_fixture", "display_name": "Access fixture"},
        )
        .status_code
        == 201
    )
    assert called == [
        ("retry", "operator@demo.local"),
        ("onboard", "operator@demo.local"),
    ]


def test_admin_can_revoke_sessions_with_audit_and_transaction_rollback(
    clients, monkeypatch
):
    viewer = one("SELECT user_id FROM obs.users WHERE email='viewer@demo.local'")[
        "user_id"
    ]
    evidence = {}

    @contextmanager
    def rolled_back():
        with connection() as conn:
            try:
                yield conn
                evidence["active"] = conn.execute(
                    "SELECT count(*) AS n FROM obs.sessions WHERE user_id=%s AND revoked_at IS NULL",
                    (viewer,),
                ).fetchone()["n"]
                evidence["audit"] = conn.execute(
                    "SELECT actor FROM obs.audit_log WHERE action='revoke_sessions' AND target=%s ORDER BY id DESC LIMIT 1",
                    (str(viewer),),
                ).fetchone()["actor"]
            finally:
                conn.rollback()

    monkeypatch.setattr(actions, "connection", rolled_back)
    response = clients["admin"].post(f"/api/users/{viewer}/revoke-sessions")
    assert response.status_code == 200
    assert evidence == {"active": 0, "audit": "admin@demo.local"}
    assert clients["viewer"].get("/api/me").status_code == 200
