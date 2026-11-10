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


@pytest.fixture
def temporary_local_user():
    from obs.auth import hasher

    created = []

    def create(role):
        email = f"test-{uuid4().hex}@example.test"
        with connection() as conn:
            user = conn.execute(
                "INSERT INTO obs.users(email,display_name,role,password_hash) VALUES(%s,'Password Test',%s,%s) RETURNING user_id",
                (email, role, hasher.hash("original password")),
            ).fetchone()
        created.append(user["user_id"])
        return {"email": email, "user_id": user["user_id"]}

    yield create
    with connection() as conn:
        for uid in created:
            conn.execute("DELETE FROM obs.sessions WHERE user_id=%s", (uid,))
            conn.execute("DELETE FROM obs.users WHERE user_id=%s", (uid,))


def test_change_password_flow(temporary_local_user) -> None:
    account = temporary_local_user("viewer")
    with TestClient(app, base_url="https://localhost") as client:
        login = client.post(
            "/api/auth/login",
            json={"email": account["email"], "password": "original password"},
        )
        assert login.status_code == 200, login.text
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        wrong = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "not-the-password",
                "new_password": "new-secret-42",
            },
        )
        assert wrong.status_code == 403
        weak = client.post(
            "/api/auth/change-password",
            json={"current_password": "original password", "new_password": "short"},
        )
        assert weak.status_code == 422
        reused = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "original password",
                "new_password": "original password",
            },
        )
        assert reused.status_code == 422
        assert reused.json()["error"]["code"] == "password_reused"
        changed = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "original password",
                "new_password": "new-secret-42",
            },
        )
        assert changed.status_code == 200, changed.text
        with TestClient(app, base_url="https://localhost") as relogin:
            ok = relogin.post(
                "/api/auth/login",
                json={"email": account["email"], "password": "new-secret-42"},
            )
            assert ok.status_code == 200, ok.text


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


def test_admin_password_reset(clients: dict, temporary_local_user) -> None:
    account = temporary_local_user("operator")
    reset = clients["admin"].post(f"/api/users/{account['user_id']}/reset-password")
    assert reset.status_code == 200, reset.text
    temporary = reset.json()["temporary_password"]
    assert temporary
    with TestClient(app, base_url="https://localhost") as fresh:
        login = fresh.post(
            "/api/auth/login",
            json={"email": account["email"], "password": temporary},
        )
        assert login.status_code == 200, login.text
        fresh.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        changed = fresh.post(
            "/api/auth/change-password",
            json={
                "current_password": temporary,
                "new_password": "a secure replacement password",
            },
        )
        assert changed.status_code == 200, changed.text


def test_workflow_trigger_and_warehouse(clients: dict) -> None:
    operator = clients["operator"]
    workflow = operator.get("/api/tenants/acme_retail/workflow")
    assert workflow.status_code == 200, workflow.text
    body = workflow.json()
    assert body["tenant_id"] == "acme_retail"
    assert {s["source"] for s in body["sources"]} == {"mysql", "mongo"}
    tenant_id = f"trigger_test_{uuid4().hex[:12]}"
    with connection() as conn:
        conn.execute(
            "INSERT INTO obs.tenants(tenant_id,display_name,status) VALUES(%s,%s,'active')",
            (tenant_id, "Trigger test"),
        )
    try:
        triggered = operator.post(
            f"/api/tenants/{tenant_id}/trigger", json={"dag": "mysql_initial"}
        )
        assert triggered.status_code == 403, triggered.text
        locked = operator.post(
            f"/api/tenants/{tenant_id}/trigger", json={"dag": "analytics_marts"}
        )
        assert locked.status_code == 422, locked.text
        eligible = operator.post(
            "/api/tenants/acme_retail/trigger", json={"dag": "analytics_marts"}
        )
        assert eligible.status_code == 200, eligible.text
        unknown = operator.post(
            f"/api/tenants/{tenant_id}/trigger", json={"dag": "nope"}
        )
        assert unknown.status_code == 404
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.demo_jobs WHERE tenant_id=%s", (tenant_id,))
            conn.execute(
                "DELETE FROM obs.tenant_events WHERE tenant_id=%s", (tenant_id,)
            )
            conn.execute("DELETE FROM obs.tenants WHERE tenant_id=%s", (tenant_id,))
    warehouse = operator.get("/api/warehouse", params={"tenant": "acme_retail"})
    assert warehouse.status_code == 200, warehouse.text
    view = warehouse.json()
    assert view["table_count"] >= 1
    assert view["total_rows"] > 0


def test_pipeline_catalog_includes_demo_analytics(clients: dict) -> None:
    response = clients["viewer"].get("/api/pipelines/catalog")
    assert response.status_code == 200, response.text
    dags = {dag["node_id"]: dag for dag in response.json()["dags"]}
    assert {
        "coordinator",
        "mysql_provision",
        "mysql_initial",
        "mysql_cdc",
        "mongo_provision",
        "mongo_initial",
        "mongo_cdc",
        "analytics_marts",
        "analytics_rollup",
        "analytics_quality",
    } <= dags.keys()
    for node in ("analytics_marts", "analytics_rollup", "analytics_quality"):
        assert dags[node]["depends_on"] == ["mysql_initial"]
        assert dags[node]["run_policy"] == "Demo only"


def test_tenant_metrics_cover_initial_loads_and_activity(clients):
    response = clients["admin"].get("/api/tenants/acme_retail/metrics?range=24h")
    assert response.status_code == 200
    body = response.json()
    by_pipeline = {(p["source_type"], p["load_type"]): p for p in body["pipelines"]}
    # Initial loads ran at onboarding, inside the range: they must be present
    # even though the latest-200 timeline page is full of CDC runs.
    assert by_pipeline[("mysql", "initial")]["runs"] >= 1
    assert by_pipeline[("mysql", "initial")]["avg_s"] > 0
    assert by_pipeline[("mysql", "cdc")]["runs"] >= 1
    assert body["activity"], "expected hourly activity buckets"
    assert sum(b["failed"] for b in body["activity"]) >= 1  # Acme's outage
    assert clients["admin"].get("/api/tenants/nope/metrics").status_code == 404


def test_alerts_can_filter_by_tenant(clients):
    response = clients["admin"].get("/api/alerts?tenant=northwind")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert all(item["tenant_id"] == "northwind" for item in body["items"])
    empty = clients["admin"].get("/api/alerts?tenant=acme_retail&state=firing")
    assert empty.status_code == 200
    assert all(item["tenant_id"] == "acme_retail" for item in empty.json()["items"])


def test_failures_heatmap_accepts_viewer_timezone(clients):
    utc = clients["admin"].get("/api/metrics/failures-heatmap?range=7d&tz=UTC")
    assert utc.status_code == 200
    ist = clients["admin"].get("/api/metrics/failures-heatmap?range=7d&tz=Asia/Kolkata")
    assert ist.status_code == 200
    # Same failures, different local buckets: the two grids must not be identical
    # for a dataset spanning many hours (Acme fails around the clock).
    assert utc.json()["items"] != ist.json()["items"]
    bogus = clients["admin"].get("/api/metrics/failures-heatmap?range=7d&tz=Not/AZone")
    assert bogus.status_code == 200
    assert bogus.json()["items"] == utc.json()["items"]
