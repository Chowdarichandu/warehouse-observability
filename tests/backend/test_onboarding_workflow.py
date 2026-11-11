from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from obs.api.schemas import OnboardInput, OnboardProgress
from obs.db import connection, one, rows
from obs.onboarding import workflow
from obs.provision import resource
from obs.integrations.http import UpstreamError


@pytest.fixture
def tracked_tenant():
    tenant = "workflow_" + uuid4().hex[:10]
    data = OnboardInput(tenant_id=tenant, display_name="Workflow Fixture")
    with connection() as conn:
        conn.execute(
            "INSERT INTO obs.tenants(tenant_id,display_name,status) VALUES(%s,%s,'onboarding')",
            (tenant, data.display_name),
        )
        conn.execute(
            "INSERT INTO obs.onboarding_requests(tenant_id,payload) VALUES(%s,%s)",
            (tenant, Jsonb(data.model_dump())),
        )
        workflow_id = workflow.initialize(conn, data)
    yield tenant, workflow_id, data
    with connection() as conn:
        conn.execute(
            "DELETE FROM obs.onboarding_dag_attempts WHERE workflow_id=%s",
            (workflow_id,),
        )
        conn.execute(
            "DELETE FROM obs.onboarding_workflows WHERE workflow_id=%s", (workflow_id,)
        )
        for table in (
            "quality_results",
            "onboarding_requests",
            "provisioning_resources",
            "pipeline_runs",
            "warehouse_snapshots",
            "schema_snapshots",
            "tenant_events",
            "demo_jobs",
        ):
            conn.execute(f"DELETE FROM obs.{table} WHERE tenant_id=%s", (tenant,))
        conn.execute(
            "DELETE FROM obs.quality_checks WHERE tenant_id=%s",
            (tenant,),
        )
        conn.execute("DELETE FROM obs.incidents WHERE tenant_id=%s", (tenant,))
        conn.execute("DELETE FROM obs.tenants WHERE tenant_id=%s", (tenant,))


def tick(tenant, data, step):
    with connection() as conn:
        return workflow.demo_tick(
            conn,
            {"tenant_id": tenant, "payload": data.model_dump(), "step": step},
            datetime.now(UTC) + timedelta(seconds=step),
        )


def mark_workflow_ready(tenant: str, workflow_id: str, *, shared_mongo: bool) -> None:
    """Make the DAG side complete so activation tests isolate the quality gate."""
    with connection() as conn:
        conn.execute(
            "UPDATE obs.tenants SET sources=%s,has_mongo=%s WHERE tenant_id=%s",
            (
                Jsonb(
                    {"mongo": {"shared": True, "tenant_field": "tenant_id"}}
                    if shared_mongo
                    else {"mysql": {"database_per_tenant": True}}
                ),
                shared_mongo,
                tenant,
            ),
        )
        for node in workflow.latest(conn, workflow_id):
            if node["node_id"] != "coordinator":
                workflow.update_node(
                    conn,
                    workflow_id,
                    node["node_id"],
                    "success",
                    reason="Isolation gate test fixture",
                )


def isolation_check(tenant: str) -> int:
    with connection() as conn:
        return conn.execute(
            """INSERT INTO obs.quality_checks
            (tenant_id,name,table_name,kind,params,sample_limit)
            VALUES(%s,%s,'orders','tenant_isolation',%s,100) RETURNING id""",
            (
                tenant,
                "Isolation gate " + uuid4().hex,
                Jsonb({"tenant_field": "tenant_id"}),
            ),
        ).fetchone()["id"]


def add_isolation_result(
    check_id: int, tenant: str, status: str, checked_at=None
) -> None:
    with connection() as conn:
        conn.execute(
            """INSERT INTO obs.quality_results
            (check_id,tenant_id,status,sampled_rows,details,simulated,checked_at)
            VALUES(%s,%s,%s,0,%s,false,coalesce(%s,now()))""",
            (check_id, tenant, status, Jsonb({"foreign_rows": 0}), checked_at),
        )


def test_live_activation_requires_current_workflow_isolation_pass(
    tracked_tenant, monkeypatch
):
    tenant, workflow_id, _ = tracked_tenant
    monkeypatch.setattr(workflow, "settings", lambda: SimpleNamespace(mode="live"))
    mark_workflow_ready(tenant, workflow_id, shared_mongo=True)
    check_id = isolation_check(tenant)

    assert workflow.activate(tenant, actor="test") is False
    assert (
        one("SELECT status FROM obs.tenants WHERE tenant_id=%s", (tenant,))["status"]
        == "onboarding"
    )

    add_isolation_result(check_id, tenant, "fail")
    assert workflow.activate(tenant, actor="test") is False
    assert (
        one("SELECT status FROM obs.tenants WHERE tenant_id=%s", (tenant,))["status"]
        == "onboarding"
    )

    add_isolation_result(check_id, tenant, "pass")
    assert workflow.activate(tenant, actor="test") is True
    assert (
        one("SELECT status FROM obs.tenants WHERE tenant_id=%s", (tenant,))["status"]
        == "active"
    )


def test_live_activation_rejects_stale_isolation_evidence(tracked_tenant, monkeypatch):
    tenant, workflow_id, _ = tracked_tenant
    monkeypatch.setattr(workflow, "settings", lambda: SimpleNamespace(mode="live"))
    mark_workflow_ready(tenant, workflow_id, shared_mongo=True)
    check_id = isolation_check(tenant)
    add_isolation_result(
        check_id,
        tenant,
        "pass",
        checked_at=datetime.now(UTC) - timedelta(hours=1),
    )

    assert workflow.activate(tenant, actor="test") is False
    assert (
        one("SELECT status FROM obs.tenants WHERE tenant_id=%s", (tenant,))["status"]
        == "onboarding"
    )


def test_live_sql_only_activation_does_not_require_mongo_isolation(
    tracked_tenant, monkeypatch
):
    tenant, workflow_id, _ = tracked_tenant
    monkeypatch.setattr(workflow, "settings", lambda: SimpleNamespace(mode="live"))
    mark_workflow_ready(tenant, workflow_id, shared_mongo=False)

    assert workflow.activate(tenant, actor="test") is True
    assert (
        one("SELECT status FROM obs.tenants WHERE tenant_id=%s", (tenant,))["status"]
        == "active"
    )


def test_demo_tracks_seven_dags_parallel_branches_and_first_cdc(tracked_tenant):
    tenant, workflow_id, data = tracked_tenant
    assert len(workflow.progress(tenant)["dags"]) == 7
    tick(tenant, data, 0)
    state = workflow.progress(tenant)
    assert {n["node_id"] for n in state["dags"] if n["status"] == "running"} == {
        "coordinator",
        "mysql_provision",
        "mongo_provision",
    }
    for step in (1, 2):
        assert not tick(tenant, data, step)
    state = workflow.progress(tenant)
    assert state["status"] == "onboarding"
    assert {n["node_id"] for n in state["dags"] if n["status"] == "running"} == {
        "coordinator",
        "mysql_initial",
        "mongo_initial",
    }
    tick(tenant, data, 3)
    assert (
        one("SELECT status FROM obs.tenants WHERE tenant_id=%s", (tenant,))["status"]
        == "onboarding"
    )
    assert tick(tenant, data, 4)
    state = OnboardProgress.model_validate(workflow.progress(tenant))
    assert state.workflow_id == workflow_id
    assert state.status == "active" and state.workflow_status == "success"
    assert all(n.status == "success" and n.dag_run_id for n in state.dags)
    coordinator = state.dags[0]
    assert all(n.parent_dag_run_id == coordinator.dag_run_id for n in state.dags[1:])
    assert all(n.run_key for n in state.dags if n.phase in {"initial", "cdc"})
    assert (
        len(
            rows(
                "SELECT * FROM obs.pipeline_runs WHERE tenant_id=%s AND triggered_by='onboarding' AND status='success'",
                (tenant,),
            )
        )
        == 4
    )
    assert (
        len(
            one(
                "SELECT airbyte_connections FROM obs.tenants WHERE tenant_id=%s",
                (tenant,),
            )["airbyte_connections"]
        )
        == 4
    )


def test_deferred_initial_stays_onboarding_and_resumes_without_duplicate_resources(
    tracked_tenant,
):
    tenant, _, data = tracked_tenant
    data.run_initial = False
    with connection() as conn:
        conn.execute(
            "UPDATE obs.onboarding_requests SET payload=%s WHERE tenant_id=%s",
            (Jsonb(data.model_dump()), tenant),
        )
    for step in range(3):
        tick(tenant, data, step)
    state = workflow.progress(tenant)
    assert (
        state["status"] == "onboarding"
        and state["workflow_status"] == "awaiting_initial"
    )
    assert state["can_resume"]
    nodes = {n["node_id"]: n for n in state["dags"]}
    assert nodes["mysql_initial"]["status"] == "awaiting_initial"
    assert (
        nodes["mysql_cdc"]["status"] == "blocked"
        and nodes["mysql_cdc"]["dag_run_id"] is None
    )
    resource_ids = rows(
        "SELECT resource_key,remote_id FROM obs.provisioning_resources WHERE tenant_id=%s ORDER BY resource_key",
        (tenant,),
    )
    resumed = workflow.resume(tenant, "operator@demo.local")
    assert resumed["dags"][0]["attempt"] == 2
    data.run_initial = True
    for step in range(5):
        tick(tenant, data, step)
    assert workflow.progress(tenant)["status"] == "active"
    assert (
        rows(
            "SELECT resource_key,remote_id FROM obs.provisioning_resources WHERE tenant_id=%s ORDER BY resource_key",
            (tenant,),
        )
        == resource_ids
    )
    assert all(n["attempt"] == 1 for n in workflow.progress(tenant)["dags"][1:])


def test_disabled_source_is_skipped_and_never_generates_sync(tracked_tenant):
    tenant, workflow_id, data = tracked_tenant
    data.has_mongo = False
    with connection() as conn:
        conn.execute(
            "UPDATE obs.tenants SET has_mongo=false WHERE tenant_id=%s", (tenant,)
        )
        conn.execute(
            "UPDATE obs.onboarding_requests SET payload=%s WHERE tenant_id=%s",
            (Jsonb(data.model_dump()), tenant),
        )
        for node in ("mongo_provision", "mongo_initial", "mongo_cdc"):
            workflow.update_node(
                conn, workflow_id, node, "skipped", reason="Source disabled"
            )
    for step in range(5):
        tick(tenant, data, step)
    state = workflow.progress(tenant)
    assert state["status"] == "active"
    assert all(
        n["status"] == "skipped" and not n["dag_run_id"]
        for n in state["dags"]
        if n["source_type"] == "mongo"
    )
    assert not rows(
        "SELECT run_key FROM obs.pipeline_runs WHERE tenant_id=%s AND source_type='mongo'",
        (tenant,),
    )


def test_confirmed_failure_resumes_new_attempt_and_retains_history(tracked_tenant):
    tenant, workflow_id, _ = tracked_tenant
    with connection() as conn:
        workflow.update_node(
            conn,
            workflow_id,
            "mysql_provision",
            "failed",
            error="Confirmed connector check failed",
        )
        conn.execute(
            "UPDATE obs.onboarding_workflows SET state='failed' WHERE workflow_id=%s",
            (workflow_id,),
        )
    assert workflow.progress(tenant)["can_resume"]
    resumed = workflow.resume(tenant, "operator@demo.local")
    mysql = next(n for n in resumed["dags"] if n["node_id"] == "mysql_provision")
    assert mysql["attempt"] == 2 and mysql["status"] == "blocked"
    assert (
        one(
            "SELECT status FROM obs.onboarding_dag_attempts WHERE workflow_id=%s AND node_id='mysql_provision' AND attempt=1",
            (workflow_id,),
        )["status"]
        == "failed"
    )


def test_uncertain_create_is_not_replayed_or_resumable(tracked_tenant):
    tenant, workflow_id, _ = tracked_tenant
    calls = []

    def unknown_create():
        calls.append(1)
        raise TimeoutError("Upstream acknowledgement missing")

    with pytest.raises(TimeoutError):
        resource(tenant, "mysql:source", unknown_create)
    with pytest.raises(RuntimeError, match="reconciliation"):
        resource(tenant, "mysql:source", lambda: calls.append(2))
    assert calls == [1]
    with connection() as conn:
        conn.execute(
            "UPDATE obs.onboarding_workflows SET state='failed' WHERE workflow_id=%s",
            (workflow_id,),
        )
    assert not workflow.progress(tenant)["can_resume"]
    with pytest.raises(workflow.WorkflowError) as exc:
        workflow.resume(tenant, "operator@demo.local")
    assert exc.value.status == 409


def test_definitive_rejected_create_can_be_retried_once(tracked_tenant):
    tenant, _, _ = tracked_tenant
    with pytest.raises(UpstreamError):
        resource(
            tenant, "mysql:source", lambda: (_ for _ in ()).throw(UpstreamError(400))
        )
    calls = []
    assert (
        resource(tenant, "mysql:source", lambda: calls.append(1) or "confirmed-id")
        == "confirmed-id"
    )
    assert (
        resource(tenant, "mysql:source", lambda: calls.append(2) or "duplicate")
        == "confirmed-id"
    )
    assert calls == [1]


def test_reference_only_execution_rejects_raw_conf_and_wrong_run(tracked_tenant):
    tenant, workflow_id, _ = tracked_tenant
    with pytest.raises(ValueError, match="references only"):
        workflow.execution(
            {
                "tenant_id": tenant,
                "workflow_id": workflow_id,
                "password": "never-store",
            },
            "dag",
            "run",
        )
    with pytest.raises(ValueError, match="persisted"):
        workflow.execution(
            {
                "tenant_id": tenant,
                "workflow_id": workflow_id,
                "node_id": "coordinator",
                "attempt": 1,
            },
            "wrong-dag",
            "run",
        )


def test_live_coordinator_observes_real_outcomes_and_never_duplicates_dag_run(
    tracked_tenant, monkeypatch
):
    tenant, workflow_id, _ = tracked_tenant
    remote = {}
    posts = []

    class FakeAirflow:
        def __init__(self, **kwargs):
            pass

        def dag_run(self, dag_id, run_id):
            if (dag_id, run_id) not in remote:
                raise UpstreamError(404)
            return remote[(dag_id, run_id)]

        def tasks(self, dag_id, run_id):
            return [
                {
                    "task_id": "provision",
                    "state": remote[(dag_id, run_id)]["state"],
                    "map_index": -1,
                }
            ]

        def trigger_workflow_dag(self, dag_id, run_id, conf):
            posts.append((dag_id, run_id, conf))
            remote[(dag_id, run_id)] = {"state": "queued"}

    monkeypatch.setattr(workflow, "Airflow", FakeAirflow)
    monkeypatch.setattr(workflow, "require_live", lambda: None)
    workflow.trigger_node(workflow_id, "coordinator")
    workflow.trigger_node(workflow_id, "coordinator")
    assert len(posts) == 1
    assert not workflow.advance_live(tenant)
    assert {post[2]["node_id"] for post in posts} == {
        "coordinator",
        "mysql_provision",
        "mongo_provision",
    }
    mysql = next(post for post in posts if post[2]["node_id"] == "mysql_provision")
    remote[(mysql[0], mysql[1])] = {"state": "success"}
    assert not workflow.advance_live(tenant)
    assert "mysql_initial" in {post[2]["node_id"] for post in posts}
    assert "mongo_initial" not in {post[2]["node_id"] for post in posts}
    assert "mysql_cdc" not in {post[2]["node_id"] for post in posts}
    count = len(posts)
    assert not workflow.advance_live(tenant)
    assert len(posts) == count
    assert workflow.progress(tenant)["status"] == "onboarding"


def test_ambiguous_dag_trigger_is_not_replayed_and_get_can_reconcile(
    tracked_tenant, monkeypatch
):
    tenant, workflow_id, _ = tracked_tenant
    posts = []

    class FakeAirflow:
        def __init__(self, **kwargs):
            pass

        def dag_run(self, dag_id, run_id):
            if not posts:
                raise UpstreamError(404)
            return {"state": "running"}

        def tasks(self, dag_id, run_id):
            return [{"task_id": "validate_request", "state": "success"}]

        def trigger_workflow_dag(self, *args):
            posts.append(args)
            raise UpstreamError(503, ambiguous=True)

    monkeypatch.setattr(workflow, "Airflow", FakeAirflow)
    monkeypatch.setattr(workflow, "require_live", lambda: None)
    workflow.trigger_node(workflow_id, "coordinator")
    assert workflow.progress(tenant)["workflow_status"] == "uncertain"
    workflow.trigger_node(workflow_id, "coordinator")
    assert len(posts) == 1
    with connection() as conn:
        node = next(
            n
            for n in workflow.latest(conn, workflow_id)
            if n["node_id"] == "coordinator"
        )
    workflow.observe(workflow_id, node)
    workflow.refresh_state(workflow_id)
    assert workflow.progress(tenant)["workflow_status"] == "running"
    assert len(posts) == 1


def test_airflow_worker_profile_requires_tls_and_flags_without_console_secrets():
    from pydantic import ValidationError
    from obs.settings import Settings

    values = dict(
        _env_file=None,
        mode="live",
        service_kind="airflow_worker",
        database_url="postgresql://obs@db/obs?sslmode=verify-full",
        live_actions_enabled=True,
        registry_dags_enabled=True,
    )
    assert Settings(**values).service_kind == "airflow_worker"
    with pytest.raises(ValidationError, match="verify-full"):
        Settings(**{**values, "database_url": "postgresql://obs@db/obs"})
    with pytest.raises(ValidationError, match="explicitly enabled"):
        Settings(**{**values, "live_actions_enabled": False})
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(**{**values, "service_kind": "console"})
