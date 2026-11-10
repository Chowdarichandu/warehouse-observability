from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from obs.api.main import app
from obs.db import connection, one, rows
from obs.demo.seed import seed


@pytest.mark.parametrize(
    "path",
    [
        "/overview",
        "/tenants",
        "/tenants/acme_retail",
        "/tenants/acme_retail/timeline",
        "/runs",
        "/errors/groups?range=7d",
        "/metrics/durations",
        "/metrics/mttr",
        "/metrics/failures-heatmap",
        "/freshness",
        "/volume-anomalies",
        "/schema-changes",
        "/alerts",
        "/alert-rules",
        "/channels",
        "/platform/health",
        "/search?q=binlog",
        "/audit",
        "/users",
    ],
)
def test_read_contracts(clients: dict, path: str) -> None:
    response = clients["admin"].get("/api" + path)
    assert response.status_code == 200, response.text


def test_authentication_and_csrf(clients: dict) -> None:
    with TestClient(app) as anonymous:
        response = anonymous.get("/api/tenants")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"
    response = clients["admin"].post(
        "/api/channels/slack-data-eng/test", headers={"X-CSRF-Token": "wrong"}
    )
    assert response.status_code == 403
    response = clients["admin"].post(
        "/api/channels/slack-data-eng/test", headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403


def test_roles_are_enforced_on_server(clients: dict) -> None:
    assert clients["viewer"].get("/api/audit").status_code == 403
    assert (
        clients["viewer"]
        .post(
            "/api/onboarding/preflight",
            json={"tenant_id": "test_tenant", "display_name": "Test Tenant"},
        )
        .status_code
        == 403
    )
    assert (
        clients["operator"]
        .patch("/api/tenants/acme_retail", json={"status": "paused"})
        .status_code
        == 403
    )
    assert clients["operator"].get("/api/alert-rules").status_code == 403


def test_pagination_filters_and_sort(clients: dict) -> None:
    response = clients["admin"].get(
        "/api/runs?status=failed&tenant=acme_retail&page_size=2&sort=started_at"
    )
    data = response.json()
    assert len(data["items"]) == 2 and data["total"] > 2
    assert all(
        r["status"] == "failed" and r["tenant_id"] == "acme_retail"
        for r in data["items"]
    )
    second = (
        clients["admin"]
        .get(
            "/api/runs?status=failed&tenant=acme_retail&page_size=2&sort=started_at&page=2"
        )
        .json()
    )
    assert not {r["run_key"] for r in data["items"]} & {
        r["run_key"] for r in second["items"]
    }
    assert (
        clients["admin"].get("/api/runs?sort=duration_s;DROP TABLE").status_code == 422
    )
    assert clients["admin"].get("/api/runs?page_size=999").status_code == 422


def test_csv_exports_whole_filtered_range(clients: dict) -> None:
    response = clients["admin"].get(
        "/api/runs?tenant=acme_retail&status=failed&format=csv"
    )
    count = (
        clients["admin"]
        .get("/api/runs?tenant=acme_retail&status=failed")
        .json()["total"]
    )
    assert response.headers["content-type"].startswith("text/csv")
    assert len(response.text.splitlines()) == count + 1


def test_scenarios_and_log_boundary(clients: dict) -> None:
    data = clients["admin"].get("/api/tenants/acme_retail").json()
    assert data["health"]["health"] == "down"
    latest = next(
        r
        for r in data["health"]["latest_runs"]
        if r["source_type"] == "mysql" and r["load_type"] == "cdc"
    )
    run = clients["admin"].get("/api/runs/" + latest["run_key"]).json()
    assert run["error"]["error_class"] == "MYSQL_BINLOG_PURGED"
    assert "resync" in run["error"]["hint"].lower()
    log = (
        clients["admin"]
        .get("/api/runs/" + latest["run_key"] + "/log")
        .json()["content"]
    )
    assert "demo-password" not in log and "demo-sensitive-token" not in log
    assert "[REDACTED]" in log and "[EMAIL]" in log
    assert (
        one("SELECT count(*) AS n FROM obs.v_stuck_runs WHERE tenant_id='northwind'")[
            "n"
        ]
        >= 1
    )
    assert any(
        v["tenant_id"] == "orbit_logistics" and v["change_pct"] < -39
        for v in clients["admin"].get("/api/volume-anomalies").json()["items"]
    )
    assert clients["admin"].get("/api/schema-changes").json()["items"][0]["added"] == [
        "delivery_region"
    ]
    assert (
        one(
            "SELECT count(*) AS n FROM obs.platform_health WHERE component='airflow_import_errors' AND status='degraded'"
        )["n"]
        > 0
    )


def test_metric_definition_matches_raw_runs(clients: dict) -> None:
    end = datetime.now(UTC)
    start = end - timedelta(hours=24)
    raw = one(
        """SELECT count(*) FILTER(WHERE status='success') AS success,count(*) FILTER(WHERE status='failed') AS failed,
        avg(duration_s) FILTER(WHERE status='success' AND load_type='cdc')/60 AS avg FROM obs.pipeline_runs
        WHERE started_at>=%s AND started_at<%s""",
        (start, end),
    )
    data = (
        clients["admin"]
        .get("/api/overview", params={"from": start.isoformat(), "to": end.isoformat()})
        .json()["kpis"]
    )
    assert data["success_rate"] == round(
        100 * raw["success"] / (raw["success"] + raw["failed"]), 2
    )
    assert data["cdc_avg_min"] == round(float(raw["avg"]), 2)


def test_seed_is_idempotent() -> None:
    before = one("SELECT count(*) AS n FROM obs.pipeline_runs")["n"]
    seed()
    assert one("SELECT count(*) AS n FROM obs.pipeline_runs")["n"] == before
    assert not rows(
        "SELECT run_key,count(*) FROM obs.pipeline_runs GROUP BY run_key HAVING count(*)>1"
    )


def test_retry_is_audited_and_idempotent(clients: dict) -> None:
    key = one(
        "SELECT run_key FROM obs.pipeline_runs WHERE tenant_id='acme_retail' AND status='failed' ORDER BY started_at DESC LIMIT 1"
    )["run_key"]
    first = clients["operator"].post("/api/runs/" + key + "/retry")
    second = clients["operator"].post("/api/runs/" + key + "/retry")
    assert first.status_code == second.status_code == 200
    assert first.json()["run_key"] == second.json()["run_key"]
    assert (
        one(
            "SELECT count(*) AS n FROM obs.audit_log WHERE action='retry_run' AND target=%s",
            (key,),
        )["n"]
        >= 1
    )


def test_never_accept_onboarding_passwords(clients: dict) -> None:
    body = {
        "tenant_id": "test_tenant",
        "display_name": "Test",
        "password": "do-not-store",
    }
    assert clients["operator"].post("/api/onboarding", json=body).status_code == 422
    body.pop("password")
    body["mysql_secret_ref"] = "mysql://user:password@host"
    assert (
        clients["operator"].post("/api/onboarding/preflight", json=body).status_code
        == 422
    )


def test_pause_resume_and_audit(clients: dict) -> None:
    tenant = "test_" + uuid4().hex[:8]
    with connection() as conn:
        conn.execute(
            "INSERT INTO obs.tenants(tenant_id,display_name,status) VALUES(%s,'Test','active')",
            (tenant,),
        )
    try:
        assert (
            clients["admin"]
            .patch("/api/tenants/" + tenant, json={"status": "paused"})
            .status_code
            == 200
        )
        assert (
            one("SELECT status FROM obs.tenants WHERE tenant_id=%s", (tenant,))[
                "status"
            ]
            == "paused"
        )
        assert (
            clients["admin"]
            .patch("/api/tenants/" + tenant, json={"status": "active"})
            .status_code
            == 200
        )
        assert (
            one("SELECT count(*) AS n FROM obs.audit_log WHERE target=%s", (tenant,))[
                "n"
            ]
            == 2
        )
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.tenants WHERE tenant_id=%s", (tenant,))


def test_change_password_flow(clients: dict) -> None:
    import os

    from fastapi.testclient import TestClient

    from obs.api.main import app

    client = TestClient(app, base_url="https://localhost")
    password = os.getenv("DEMO_PASSWORD", "demo")
    login = client.post(
        "/api/auth/login",
        json={"email": "viewer@demo.local", "password": password},
    )
    assert login.status_code == 200, login.text
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    wrong = client.post(
        "/api/auth/change-password",
        json={"current_password": "not-the-password", "new_password": "new-secret-42"},
    )
    assert wrong.status_code == 401
    weak = client.post(
        "/api/auth/change-password",
        json={"current_password": password, "new_password": "short"},
    )
    assert weak.status_code == 422
    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": password, "new_password": "new-secret-42"},
    )
    assert changed.status_code == 200, changed.text
    relogin = TestClient(app, base_url="https://localhost")
    ok = relogin.post(
        "/api/auth/login",
        json={"email": "viewer@demo.local", "password": "new-secret-42"},
    )
    assert ok.status_code == 200, ok.text
    # Restore the shared demo password so other tests keep working.
    relogin.headers["X-CSRF-Token"] = ok.json()["csrf_token"]
    restored = relogin.post(
        "/api/auth/change-password",
        json={"current_password": "new-secret-42", "new_password": password},
    )
    assert restored.status_code == 200, restored.text
    client.close()
    relogin.close()


def test_roles_reset_and_trigger(clients: dict) -> None:
    admin = clients["admin"]
    roles = admin.get("/api/roles")
    assert roles.status_code == 200, roles.text
    names = {r["name"] for r in roles.json()}
    assert {"viewer", "operator", "admin"} <= names
    created = admin.post(
        "/api/roles",
        json={
            "name": "support_engineer",
            "base_level": "operator",
            "permissions": ["trigger_pipelines", "manage_alerts"],
            "description": "On-call support",
        },
    )
    assert created.status_code == 201, created.text
    assert "view_console" in created.json()["permissions"]
    users = admin.get("/api/users").json()["items"]
    viewer = next(u for u in users if u["email"] == "viewer@demo.local")
    assigned = admin.patch(
        f"/api/users/{viewer['user_id']}", json={"role_name": "support_engineer"}
    )
    assert assigned.status_code == 200, assigned.text
    me = clients["viewer"].get("/api/me")
    assert me.status_code == 200
    assert me.json()["role_name"] == "support_engineer"
    assert "trigger_pipelines" in me.json()["permissions"]
    assert "manage_users" not in me.json()["permissions"]
    # Restore the viewer to the plain system role for other tests.
    restored = admin.patch(f"/api/users/{viewer['user_id']}", json={"role": "viewer"})
    assert restored.status_code == 200
    deleted = admin.delete("/api/roles/support_engineer")
    assert deleted.status_code == 200, deleted.text


def test_admin_password_reset(clients: dict) -> None:
    import os

    from fastapi.testclient import TestClient

    from obs.api.main import app

    admin = clients["admin"]
    users = admin.get("/api/users").json()["items"]
    operator = next(u for u in users if u["email"] == "operator@demo.local")
    reset = admin.post(f"/api/users/{operator['user_id']}/reset-password")
    assert reset.status_code == 200, reset.text
    temporary = reset.json()["temporary_password"]
    assert temporary
    fresh = TestClient(app, base_url="https://localhost")
    login = fresh.post(
        "/api/auth/login",
        json={"email": "operator@demo.local", "password": temporary},
    )
    assert login.status_code == 200, login.text
    fresh.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    back = fresh.post(
        "/api/auth/change-password",
        json={
            "current_password": temporary,
            "new_password": os.getenv("DEMO_PASSWORD", "demo"),
        },
    )
    assert back.status_code == 200, back.text
    fresh.close()


def test_workflow_trigger_and_warehouse(clients: dict) -> None:
    operator = clients["operator"]
    workflow = operator.get("/api/tenants/acme_retail/workflow")
    assert workflow.status_code == 200, workflow.text
    body = workflow.json()
    assert body["tenant_id"] == "acme_retail"
    assert {s["source"] for s in body["sources"]} == {"mysql", "mongo"}
    triggered = operator.post(
        "/api/tenants/acme_retail/trigger", json={"dag": "mysql_initial"}
    )
    assert triggered.status_code == 200, triggered.text
    unknown = operator.post("/api/tenants/acme_retail/trigger", json={"dag": "nope"})
    assert unknown.status_code == 404
    warehouse = operator.get("/api/warehouse", params={"tenant": "acme_retail"})
    assert warehouse.status_code == 200, warehouse.text
    view = warehouse.json()
    assert view["table_count"] >= 1
    assert view["total_rows"] > 0


def test_pipeline_catalog(clients: dict) -> None:
    response = clients["viewer"].get("/api/pipelines/catalog")
    assert response.status_code == 200, response.text
    body = response.json()
    node_ids = {d["node_id"] for d in body["dags"]}
    assert {
        "coordinator",
        "mysql_provision",
        "mysql_initial",
        "mysql_cdc",
        "mongo_provision",
        "mongo_initial",
        "mongo_cdc",
        "analytics_marts",
    } <= node_ids
    mysql_cdc = next(d for d in body["dags"] if d["node_id"] == "mysql_cdc")
    assert mysql_cdc["dag_id"] == "mysql_cdc"
    assert mysql_cdc["depends_on"] == ["mysql_initial"]
    assert mysql_cdc["latest_status"] in {"success", "failed", "running", None}
