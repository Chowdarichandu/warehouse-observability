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


def test_custom_role_capabilities_and_minimum_role_fail_closed(monkeypatch):
    import obs.auth as auth

    monkeypatch.setattr(
        auth, "one", lambda *args: {"permissions": ["view_console", "manage_tenants"]}
    )
    custom = auth.user_permissions({"role": "operator", "role_name": "support"})
    policy = {item["id"]: item for item in permissions("operator", settings(), custom)}
    assert policy["onboarding.start"]["enabled"]
    assert not policy["pipelines.retry"]["allowed"]
    assert not policy["tenants.configure"]["allowed"]
    with pytest.raises(HTTPException):
        auth.require_role("operator", "trigger_pipelines")(
            {"role": "operator", "permissions": custom}
        )
    with pytest.raises(HTTPException):
        auth.require_permission("manage_users")(
            {"role": "operator", "permissions": ["manage_users"]}
        )
    monkeypatch.setattr(auth, "one", lambda *args: None)
    assert auth.user_permissions({"role": "admin", "role_name": "missing"}) == []
    assert auth.user_permissions({"role": "unrecognized"}) == []


def test_custom_operator_cannot_resume_onboarding_without_tenant_permission():
    from obs.auth import current_user

    app.dependency_overrides[current_user] = lambda: {
        "role": "operator",
        "permissions": ["view_console"],
        "email": "restricted@example.test",
    }
    try:
        client = TestClient(app, base_url="https://localhost")
        response = client.post("/api/onboarding/system_engines/resume", json={})
        assert response.status_code == 403
        client.close()
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_restricted_user_manager_cannot_grant_or_reset_higher_privileges(monkeypatch):
    from obs.api.schemas import RoleIn, UserPatch
    from obs.auth import SYSTEM_ROLE_PERMISSIONS

    restricted = {
        "role": "admin",
        "permissions": ["view_console", "manage_users"],
        "email": "limited@example.test",
    }
    with pytest.raises(HTTPException) as error:
        actions.create_role(
            RoleIn(
                name="elevated", base_level="admin", permissions=["manage_platform"]
            ),
            restricted,
        )
    assert error.value.status_code == 403

    class Result:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Conn:
        def execute(self, query, params=None):
            if "SELECT * FROM obs.users" in query:
                return Result(
                    {
                        "user_id": 42,
                        "email": "admin@example.test",
                        "role": "admin",
                        "role_name": None,
                    }
                )
            return Result()

    @contextmanager
    def fake_connection():
        yield Conn()

    monkeypatch.setattr(actions, "connection", fake_connection)
    with pytest.raises(HTTPException) as error:
        actions.update_user(42, UserPatch(role="admin"), restricted)
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        actions.reset_password(42, restricted)
    assert error.value.status_code == 403
    # A full administrator retains authority over the built-in admin bundle.
    actions._check_grantable(
        {"role": "admin", "permissions": SYSTEM_ROLE_PERMISSIONS["admin"]},
        "admin",
        SYSTEM_ROLE_PERMISSIONS["admin"],
    )


def test_forgot_password_is_disabled_by_default_without_touching_accounts(monkeypatch):
    from obs.api.routers import auth
    from obs.api.schemas import ForgotPasswordIn

    monkeypatch.setattr(settings(), "demo_unsafe_self_service_password_reset", False)
    monkeypatch.setattr(auth, "check_login_rate", lambda request: None)
    monkeypatch.setattr(
        auth, "one", lambda *args: pytest.fail("Unexpected account lookup")
    )
    result = auth.forgot_password(ForgotPasswordIn(email="admin@demo.local"), None)
    assert result["temporary_password"] is None


def test_admin_can_create_and_remove_user(clients):
    created = clients["admin"].post(
        "/api/users",
        json={
            "email": "newhire@demo.local",
            "display_name": "New Hire",
            "role": "operator",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["temporary_password"]
    user_id = body["user_id"]
    # The new account can sign in with the generated temporary password.
    guest = TestClient(app, base_url="https://localhost")
    login = guest.post(
        "/api/auth/login",
        json={"email": "newhire@demo.local", "password": body["temporary_password"]},
    )
    assert login.status_code == 200, login.text
    guest.close()
    duplicate = clients["admin"].post(
        "/api/users",
        json={"email": "newhire@demo.local", "display_name": "Dup", "role": "viewer"},
    )
    assert duplicate.status_code == 409
    removed = clients["admin"].delete(f"/api/users/{user_id}")
    assert removed.status_code == 200
    assert clients["admin"].delete(f"/api/users/{user_id}").status_code == 404


def test_create_user_with_chosen_password_returns_no_temporary(clients):
    created = clients["admin"].post(
        "/api/users",
        json={
            "email": "chosen@demo.local",
            "display_name": "Chosen Password",
            "role": "viewer",
            "initial_password": "a-strong-passphrase",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["temporary_password"] is None
    clients["admin"].delete(f"/api/users/{created.json()['user_id']}")


def test_non_admin_cannot_create_or_remove_users(clients):
    payload = {"email": "nope@demo.local", "display_name": "Nope", "role": "viewer"}
    assert clients["viewer"].post("/api/users", json=payload).status_code == 403
    assert clients["operator"].post("/api/users", json=payload).status_code == 403
    assert clients["viewer"].delete("/api/users/1").status_code == 403


def test_admin_cannot_remove_own_account(clients):
    me = clients["admin"].get("/api/me").json()
    response = clients["admin"].delete(f"/api/users/{me['user_id']}")
    assert response.status_code == 409


def _permissions_user_id(email: str) -> int:
    return one("SELECT user_id FROM obs.users WHERE email=%s", (email,))["user_id"]


def test_admin_views_user_permissions(clients):
    operator = _permissions_user_id("operator@demo.local")
    response = clients["admin"].get(f"/api/users/{operator}/permissions")
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "operator"
    assert "manage_tenants" in body["bundle"]
    assert body["grants"] == [] and body["revokes"] == []
    assert body["effective"] == sorted(body["bundle"])
    assert {item["name"] for item in body["permissions"]} == {
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
    }


def test_product_module_permissions_are_explicit_and_narrow(monkeypatch):
    from fastapi import HTTPException

    from obs import auth
    from obs.api.routers import actions

    monkeypatch.setattr(auth.settings(), "auth_provider", "local")
    monkeypatch.setattr(
        auth,
        "one",
        lambda *_: {"permissions": ["view_console", "view_module_sap"]},
    )
    permissions = auth.user_permissions(
        {"role": "viewer", "role_name": "sap_analyst", "user_id": None}
    )
    assert "view_module_sap" in permissions
    assert "view_module_hrms" not in permissions
    assert "view_module_finance" not in permissions

    # Module endpoints can use the same server-side permission dependency.
    require_sap = auth.require_permission("view_module_sap")
    require_hrms = auth.require_permission("view_module_hrms")
    assert (
        require_sap({"role": "viewer", "permissions": permissions})["role"] == "viewer"
    )
    with pytest.raises(HTTPException) as denied:
        require_hrms({"role": "viewer", "permissions": permissions})
    assert denied.value.status_code == 403

    restricted_admin = {
        "role": "admin",
        "permissions": ["view_console", "manage_users"],
    }
    with pytest.raises(HTTPException) as escalation:
        actions._check_grantable(
            restricted_admin, "viewer", ["view_console", "view_module_sap"]
        )
    assert escalation.value.status_code == 403
    actions._check_grantable(
        {"role": "admin", "permissions": auth.SYSTEM_ROLE_PERMISSIONS["admin"]},
        "viewer",
        ["view_console", "view_module_sap"],
    )


def test_module_registry_filters_disabled_areas_and_honors_role_and_user_overrides(
    clients,
):
    from obs.access import module_access

    viewer_id = _permissions_user_id("viewer@demo.local")
    with connection() as conn:
        conn.execute(
            """INSERT INTO obs.roles(name,base_level,permissions,description,created_by)
            VALUES('test_viewer','viewer','[\"view_console\"]','test','test')
            ON CONFLICT(name) DO NOTHING"""
        )
        conn.execute(
            "UPDATE obs.users SET role_name='test_viewer' WHERE user_id=%s",
            (viewer_id,),
        )
        conn.execute("UPDATE obs.modules SET enabled=true WHERE module_id='hrms'")
        conn.execute(
            "INSERT INTO obs.role_modules(role_name,module_id,granted_by) VALUES('test_viewer','hrms','test') ON CONFLICT DO NOTHING"
        )
    try:
        body = clients["viewer"].get("/api/access").json()
        assert [module["module_id"] for module in body["modules"]] == ["pravah", "hrms"]

        with connection() as conn:
            conn.execute(
                """INSERT INTO obs.user_module_overrides(user_id,module_id,effect,updated_by)
                VALUES(%s,'hrms','revoke','test')
                ON CONFLICT(user_id,module_id) DO UPDATE SET effect='revoke',updated_by='test'""",
                (viewer_id,),
            )
        assert [
            module["module_id"]
            for module in module_access(
                {
                    "user_id": viewer_id,
                    "role": "viewer",
                    "permissions": ["view_console"],
                }
            )
        ] == ["pravah"]
    finally:
        with connection() as conn:
            conn.execute(
                "DELETE FROM obs.user_module_overrides WHERE user_id=%s AND module_id='hrms'",
                (viewer_id,),
            )
            conn.execute(
                "DELETE FROM obs.role_modules WHERE role_name='test_viewer' AND module_id='hrms'"
            )
            conn.execute(
                "UPDATE obs.users SET role_name=NULL WHERE user_id=%s", (viewer_id,)
            )
            conn.execute("DELETE FROM obs.roles WHERE name='test_viewer'")
            conn.execute("UPDATE obs.modules SET enabled=false WHERE module_id='hrms'")


def test_admin_module_grant_endpoint_is_audited_and_non_admin_is_denied(clients):
    with connection() as conn:
        conn.execute(
            """INSERT INTO obs.roles(name,base_level,permissions,description,created_by)
            VALUES('test_viewer','viewer','[\"view_console\"]','test','test')
            ON CONFLICT(name) DO NOTHING"""
        )
        conn.execute("UPDATE obs.modules SET enabled=true WHERE module_id='finance'")
    try:
        viewer_denied = clients["viewer"].put(
            "/api/access/roles/test_viewer/modules/finance"
        )
        assert viewer_denied.status_code == 403
        denied = clients["operator"].put("/api/access/roles/viewer/modules/finance")
        assert denied.status_code == 403
        granted = clients["admin"].put("/api/access/roles/test_viewer/modules/finance")
        assert granted.status_code == 200, granted.text
        viewer = clients["admin"].get("/api/access").json()
        assert {item["module_id"] for item in viewer["modules"]} == {
            "pravah",
            "finance",
        }
        audit_row = one(
            """SELECT action,target FROM obs.audit_log
            WHERE action='grant_role_module' AND target='test_viewer:finance'
            ORDER BY id DESC LIMIT 1"""
        )
        assert audit_row == {
            "action": "grant_role_module",
            "target": "test_viewer:finance",
        }
    finally:
        with connection() as conn:
            conn.execute(
                "DELETE FROM obs.role_modules WHERE role_name='test_viewer' AND module_id='finance'"
            )
            conn.execute("DELETE FROM obs.roles WHERE name='test_viewer'")
            conn.execute(
                "UPDATE obs.modules SET enabled=false WHERE module_id='finance'"
            )


def test_admin_can_revoke_a_role_module_grant_and_api_access_updates(clients):
    viewer_id = _permissions_user_id("viewer@demo.local")
    with connection() as conn:
        conn.execute(
            """INSERT INTO obs.roles(name,base_level,permissions,description,created_by)
            VALUES('test_viewer','viewer','[\"view_console\"]','test','test')
            ON CONFLICT(name) DO NOTHING"""
        )
        conn.execute(
            "UPDATE obs.users SET role_name='test_viewer' WHERE user_id=%s",
            (viewer_id,),
        )
        conn.execute("UPDATE obs.modules SET enabled=true WHERE module_id='hrms'")
        conn.execute(
            """INSERT INTO obs.role_modules(role_name,module_id,granted_by)
            VALUES('test_viewer','hrms','test') ON CONFLICT DO NOTHING"""
        )
    try:
        before = clients["viewer"].get("/api/access").json()
        assert [item["module_id"] for item in before["modules"]] == ["pravah", "hrms"]

        viewer_denied = clients["viewer"].delete(
            "/api/access/roles/test_viewer/modules/hrms"
        )
        assert viewer_denied.status_code == 403
        denied = clients["operator"].delete(
            "/api/access/roles/test_viewer/modules/hrms"
        )
        assert denied.status_code == 403
        revoked = clients["admin"].delete("/api/access/roles/test_viewer/modules/hrms")
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["effect"] == "revoke"
        after = clients["viewer"].get("/api/access").json()
        assert [item["module_id"] for item in after["modules"]] == ["pravah"]
        assert one(
            """SELECT 1 AS present FROM obs.audit_log
            WHERE action='revoke_role_module' AND target='test_viewer:hrms'
            ORDER BY id DESC LIMIT 1"""
        ) == {"present": 1}
    finally:
        with connection() as conn:
            conn.execute(
                "DELETE FROM obs.role_modules WHERE role_name='test_viewer' AND module_id='hrms'"
            )
            conn.execute(
                "UPDATE obs.users SET role_name=NULL WHERE user_id=%s", (viewer_id,)
            )
            conn.execute("DELETE FROM obs.roles WHERE name='test_viewer'")
            conn.execute("UPDATE obs.modules SET enabled=false WHERE module_id='hrms'")


def test_revoke_removes_permission_from_live_requests(clients, monkeypatch):
    operator = _permissions_user_id("operator@demo.local")
    called = []
    monkeypatch.setattr(
        actions, "start", lambda data, actor: called.append(data.tenant_id)
    )
    try:
        response = clients["admin"].put(
            f"/api/users/{operator}/permissions", json={"revokes": ["manage_tenants"]}
        )
        assert response.status_code == 200
        assert "manage_tenants" not in response.json()["effective"]
        denied = clients["operator"].post(
            "/api/onboarding",
            json={"tenant_id": "access_fixture", "display_name": "Access fixture"},
        )
        assert denied.status_code == 403
        assert called == []
    finally:
        clients["admin"].put(
            f"/api/users/{operator}/permissions", json={"grants": [], "revokes": []}
        )


def test_grant_above_role_rank_is_recorded_but_not_effective(clients):
    operator = _permissions_user_id("operator@demo.local")
    try:
        response = clients["admin"].put(
            f"/api/users/{operator}/permissions", json={"grants": ["manage_users"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["grants"] == ["manage_users"]
        assert "manage_users" not in body["effective"]
    finally:
        clients["admin"].put(
            f"/api/users/{operator}/permissions", json={"grants": [], "revokes": []}
        )


def test_user_permissions_guards(clients):
    admin = _permissions_user_id("admin@demo.local")
    operator = _permissions_user_id("operator@demo.local")
    assert (
        clients["admin"]
        .put(f"/api/users/{admin}/permissions", json={"revokes": ["manage_alerts"]})
        .status_code
        == 409
    )
    assert (
        clients["admin"]
        .put(f"/api/users/{operator}/permissions", json={"grants": ["fly_to_moon"]})
        .status_code
        == 422
    )
    assert (
        clients["admin"]
        .put(
            f"/api/users/{operator}/permissions",
            json={"grants": ["manage_alerts"], "revokes": ["manage_alerts"]},
        )
        .status_code
        == 422
    )
    assert (
        clients["operator"].get(f"/api/users/{operator}/permissions").status_code == 403
    )
    assert clients["admin"].get("/api/users/999999/permissions").status_code == 404


def test_users_list_reports_active_sessions(clients):
    users = clients["admin"].get("/api/users?page=1&page_size=50").json()["items"]
    by_email = {u["email"]: u for u in users}
    # The signed-in fixture clients each hold an active server-side session.
    assert by_email["admin@demo.local"]["active_sessions"] >= 1
    assert by_email["operator@demo.local"]["active_sessions"] >= 1
    assert by_email["viewer@demo.local"]["active_sessions"] >= 1
