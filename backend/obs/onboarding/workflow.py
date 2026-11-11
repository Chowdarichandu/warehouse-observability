"""Durable seven-DAG workflow. No upstream mutation is performed by a read API."""

from datetime import UTC, datetime
from uuid import uuid4

from psycopg.types.json import Jsonb

from obs.audit import audit
from obs.db import connection, notify, one, rows
from obs.integrations.airflow import Airflow
from obs.integrations.http import UpstreamError
from obs.redact import redact, redact_tree
from obs.settings import require_live, settings

NODE_IDS = [
    "coordinator",
    "mysql_provision",
    "mysql_initial",
    "mysql_cdc",
    "mongo_provision",
    "mongo_initial",
    "mongo_cdc",
]
TASKS = {
    "coordinator": [
        ("validate_request", "Validate onboarding request"),
        ("coordinate_branches", "Monitor source branches"),
        ("activate_tenant", "Activate tenant"),
    ],
    "provision": [
        ("resolve_secret", "Resolve source secret"),
        ("create_source", "Create source"),
        ("check_source", "Check source connection"),
        ("create_initial_connection", "Create initial connection"),
        ("create_cdc_connection", "Create CDC connection"),
        ("save_connections", "Save source connection IDs"),
    ],
    "initial": [
        ("resolve_connections", "Resolve initial connection"),
        ("sync", "Trigger initial sync"),
        ("wait_for_sync", "Observe initial load completion"),
    ],
    "cdc": [
        ("resolve_connections", "Resolve CDC connection"),
        ("sync", "Trigger CDC sync"),
        ("wait_for_sync", "Observe first CDC completion"),
    ],
}


class WorkflowError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def fail(status: int, code: str, message: str) -> None:
    raise WorkflowError(status, code, message)


def resolved_dag_ids() -> dict[str, str]:
    return settings().resolved_onboarding_dags()


def definitions() -> list[dict]:
    ids = resolved_dag_ids()
    result = []
    for node in NODE_IDS:
        source, phase = (None, "coordinator") if node == "coordinator" else node.split("_", 1)
        label = (
            "Onboarding coordinator"
            if not source
            else f"{'MySQL' if source == 'mysql' else 'MongoDB'} { {'provision': 'provisioning', 'initial': 'initial load', 'cdc': 'first CDC sync'}[phase] }"
        )
        result.append(
            {
                "node_id": node,
                "source_type": source,
                "phase": phase,
                "label": label,
                "dag_id": ids[node],
                "parent_node_id": None if not source else "coordinator",
            }
        )
    return result


def latest(conn, workflow_id: str) -> list[dict]:
    return conn.execute(
        "SELECT DISTINCT ON(node_id) * FROM obs.onboarding_dag_attempts WHERE workflow_id=%s ORDER BY node_id,attempt DESC",
        (workflow_id,),
    ).fetchall()


def initialize(conn, data) -> str:
    workflow_id = str(uuid4())
    conn.execute(
        "INSERT INTO obs.onboarding_workflows(workflow_id,tenant_id) VALUES(%s,%s)",
        (workflow_id, data.tenant_id),
    )
    for node in definitions():
        skipped = node["source_type"] and not getattr(data, f"has_{node['source_type']}")
        state = (
            "skipped" if skipped else "queued" if node["node_id"] == "coordinator" else "blocked"
        )
        reason = (
            "Source disabled in onboarding request"
            if skipped
            else (
                "Waiting for coordinator"
                if node["phase"] == "provision"
                else "Waiting for source provisioning"
                if node["phase"] == "initial"
                else "Waiting for successful initial load"
            )
            if state == "blocked"
            else None
        )
        tasks = [
            {"task_id": key, "label": label, "status": "skipped" if skipped else "pending"}
            for key, label in TASKS[node["phase"]]
        ]
        conn.execute(
            """INSERT INTO obs.onboarding_dag_attempts(workflow_id,node_id,dag_id,status,blocked_reason,tasks)
            VALUES(%s,%s,%s,%s,%s,%s)""",
            (workflow_id, node["node_id"], node["dag_id"], state, reason, Jsonb(tasks)),
        )
    return workflow_id


def update_node(
    conn,
    workflow_id: str,
    node_id: str,
    status: str,
    *,
    error: str | None = None,
    reason: str | None = None,
    tasks: list | None = None,
    started_at=None,
    ended_at=None,
) -> None:
    node = next(n for n in latest(conn, workflow_id) if n["node_id"] == node_id)
    conn.execute(
        """UPDATE obs.onboarding_dag_attempts SET status=%s,last_error=%s,blocked_reason=%s,
        tasks=coalesce(%s,tasks),started_at=coalesce(started_at,%s),ended_at=coalesce(%s,ended_at),updated_at=now()
        WHERE workflow_id=%s AND node_id=%s AND attempt=%s""",
        (
            status,
            redact(error)[:2000] if error else None,
            reason,
            Jsonb(tasks) if tasks is not None else None,
            started_at,
            ended_at,
            workflow_id,
            node_id,
            node["attempt"],
        ),
    )
    conn.execute(
        "UPDATE obs.onboarding_workflows SET updated_at=now() WHERE workflow_id=%s", (workflow_id,)
    )
    if node["status"] != status:
        tenant = conn.execute(
            "SELECT tenant_id FROM obs.onboarding_workflows WHERE workflow_id=%s", (workflow_id,)
        ).fetchone()["tenant_id"]
        event_state = (
            "ok"
            if status in {"success", "skipped"}
            else "failed"
            if status in {"failed", "uncertain"}
            else "started"
        )
        conn.execute(
            "INSERT INTO obs.tenant_events(tenant_id,step,status,message) VALUES(%s,%s,%s,%s)",
            (tenant, node_id, event_state, redact(error or reason or f"DAG {status}")),
        )
        notify(conn, "onboarding.step", {"tenant_id": tenant, "step": node_id, "status": status})


def task_state(
    conn, workflow_id: str, node_id: str, task_id: str, state: str, *, error: str | None = None
) -> None:
    node = next(n for n in latest(conn, workflow_id) if n["node_id"] == node_id)
    tasks = node["tasks"]
    now = datetime.now(UTC).isoformat()
    for item in tasks:
        if item["task_id"] == task_id:
            item["status"] = state
            if state == "running":
                item.setdefault("started_at", now)
            if state in {"success", "failed", "skipped"}:
                item["ended_at"] = now
            item["last_error"] = redact(error)[:2000] if error else None
    update_node(
        conn,
        workflow_id,
        node_id,
        node["status"],
        tasks=tasks,
        error=node["last_error"],
        reason=node["blocked_reason"],
    )


def progress(tenant_id: str) -> dict:
    tenant = one(
        "SELECT tenant_id,display_name,status FROM obs.tenants WHERE tenant_id=%s", (tenant_id,)
    )
    if not tenant:
        fail(404, "tenant_not_found", "Tenant not found.")
    workflow = one("SELECT * FROM obs.onboarding_workflows WHERE tenant_id=%s", (tenant_id,))
    result = {
        **tenant,
        "events": rows(
            "SELECT * FROM obs.tenant_events WHERE tenant_id=%s ORDER BY at DESC,id DESC LIMIT 200",
            (tenant_id,),
        ),
        "simulated": settings().mode == "demo",
        "dags": [],
    }
    result["events"].reverse()
    if not workflow:
        return {
            **result,
            "workflow_status": "success" if tenant["status"] == "active" else "running",
            "resume_reason": "This tenant predates tracked onboarding; no DAG completion evidence is available.",
        }
    with connection() as conn:
        nodes = {n["node_id"]: n for n in latest(conn, str(workflow["workflow_id"]))}
    for node in definitions():
        saved = nodes[node["node_id"]]
        run = (
            one(
                "SELECT run_key FROM obs.pipeline_runs WHERE tenant_id=%s AND dag_id=%s AND dag_run_id=%s ORDER BY collected_at DESC LIMIT 1",
                (tenant_id, saved["dag_id"], saved["dag_run_id"]),
            )
            if saved["dag_run_id"]
            else {}
        )
        result["dags"].append({**node, **saved, "run_key": run.get("run_key")})
    uncertain_resource = one(
        "SELECT 1 AS found FROM obs.provisioning_resources WHERE tenant_id=%s AND state IN ('creating','uncertain') LIMIT 1",
        (tenant_id,),
    )
    can_resume = (
        not uncertain_resource
        and workflow["state"] in {"failed", "awaiting_initial"}
        and (settings().mode == "demo" or settings().live_actions_enabled)
    )
    return redact_tree(
        {
            **result,
            "workflow_id": str(workflow["workflow_id"]),
            "workflow_status": workflow["state"],
            "created_at": workflow["created_at"],
            "updated_at": workflow["updated_at"],
            "can_resume": can_resume,
            "resume_reason": "Confirm upstream outcome before retrying; an unconfirmed write is never replayed."
            if workflow["state"] == "uncertain" or uncertain_resource
            else "Start the deferred initial loads to continue."
            if workflow["state"] == "awaiting_initial"
            else "Resume confirmed failed branches; completed resources and DAGs are reused."
            if workflow["state"] == "failed"
            else None,
        }
    )


def trigger_node(workflow_id: str, node_id: str) -> None:
    """Persist a claim before HTTP. A stable run ID prevents duplicate DAG runs."""
    require_live()
    with connection() as conn:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (workflow_id + node_id,)
        )
        workflow = conn.execute(
            "SELECT * FROM obs.onboarding_workflows WHERE workflow_id=%s", (workflow_id,)
        ).fetchone()
        node = next(n for n in latest(conn, workflow_id) if n["node_id"] == node_id)
        if (
            node["status"] in {"success", "skipped", "failed", "uncertain"}
            or node["request_state"] != "unsubmitted"
        ):
            return
        parent = next(n for n in latest(conn, workflow_id) if n["node_id"] == "coordinator")
        run_id = f"obs__{workflow_id.replace('-', '')}__{node_id}__a{node['attempt']}"
        conn.execute(
            "UPDATE obs.onboarding_dag_attempts SET dag_run_id=%s,parent_dag_run_id=%s,request_state='submitting',status='queued',blocked_reason=NULL,updated_at=now() WHERE workflow_id=%s AND node_id=%s AND attempt=%s",
            (
                run_id,
                None if node_id == "coordinator" else parent["dag_run_id"],
                workflow_id,
                node_id,
                node["attempt"],
            ),
        )
        audit(
            conn,
            "onboarding:coordinator",
            "onboarding.dag_requested",
            workflow["tenant_id"],
            {"node_id": node_id, "dag_run_id": run_id},
        )
    try:
        af = Airflow(write=True)
        try:
            af.dag_run(node["dag_id"], run_id)
        except UpstreamError as exc:
            if exc.status != 404:
                raise
            try:
                af.trigger_workflow_dag(
                    node["dag_id"],
                    run_id,
                    {
                        "tenant_id": workflow["tenant_id"],
                        "workflow_id": workflow_id,
                        "node_id": node_id,
                        "attempt": node["attempt"],
                    },
                )
            except UpstreamError as conflict:
                if conflict.status != 409:
                    raise
                af.dag_run(node["dag_id"], run_id)
        with connection() as conn:
            conn.execute(
                "UPDATE obs.onboarding_dag_attempts SET request_state='confirmed',updated_at=now() WHERE workflow_id=%s AND node_id=%s AND attempt=%s",
                (workflow_id, node_id, node["attempt"]),
            )
    except Exception as exc:
        ambiguous = not isinstance(exc, UpstreamError) or exc.ambiguous
        with connection() as conn:
            conn.execute(
                "UPDATE obs.onboarding_dag_attempts SET request_state=%s WHERE workflow_id=%s AND node_id=%s AND attempt=%s",
                ("uncertain" if ambiguous else "confirmed", workflow_id, node_id, node["attempt"]),
            )
            update_node(
                conn, workflow_id, node_id, "uncertain" if ambiguous else "failed", error=str(exc)
            )
            conn.execute(
                "UPDATE obs.onboarding_workflows SET state=%s WHERE workflow_id=%s",
                ("uncertain" if ambiguous else "failed", workflow_id),
            )


def _state(value: str | None) -> str:
    return {
        "success": "success",
        "failed": "failed",
        "upstream_failed": "blocked",
        "skipped": "skipped",
        "removed": "skipped",
        "queued": "queued",
        "scheduled": "queued",
        "running": "running",
        "deferred": "running",
        "up_for_reschedule": "running",
        "up_for_retry": "running",
    }.get(value or "", "pending")


def observe(workflow_id: str, node: dict) -> None:
    if not node["dag_run_id"] or node["status"] in {"success", "skipped"}:
        return
    af = Airflow()
    try:
        run = af.dag_run(node["dag_id"], node["dag_run_id"])
        observed = af.tasks(node["dag_id"], node["dag_run_id"])
    except UpstreamError as exc:
        if exc.status == 404:
            return  # Not proof that an ambiguous POST was rejected.
        raise
    state = _state(run.get("state"))
    tasks = [
        {
            "task_id": str(t["task_id"])
            + (f"[{t['map_index']}]" if t.get("map_index", -1) >= 0 else ""),
            "label": str(t["task_id"]).replace("_", " ").capitalize(),
            "status": _state(t.get("state")),
            "started_at": t.get("start_date"),
            "ended_at": t.get("end_date"),
            "last_error": "Airflow reported a failed task. Inspect its redacted log."
            if t.get("state") == "failed"
            else None,
        }
        for t in observed
    ]
    with connection() as conn:
        conn.execute(
            "SELECT workflow_id FROM obs.onboarding_workflows WHERE workflow_id=%s FOR UPDATE",
            (workflow_id,),
        )
        current = next(n for n in latest(conn, workflow_id) if n["node_id"] == node["node_id"])
        if current["attempt"] != node["attempt"] or current["dag_run_id"] != node["dag_run_id"]:
            return  # A late observation of an old attempt cannot overwrite a resumed run.
        conn.execute(
            "UPDATE obs.onboarding_dag_attempts SET request_state='confirmed' WHERE workflow_id=%s AND node_id=%s AND attempt=%s",
            (workflow_id, node["node_id"], node["attempt"]),
        )
        update_node(
            conn,
            workflow_id,
            node["node_id"],
            state,
            tasks=tasks or node["tasks"],
            started_at=run.get("start_date"),
            ended_at=run.get("end_date"),
            error="Airflow reported a failed DAG run." if state == "failed" else None,
        )


def refresh_state(workflow_id: str) -> str:
    with connection() as conn:
        nodes = latest(conn, workflow_id)
        states = {n["node_id"]: n["status"] for n in nodes}
        uncertain = conn.execute(
            "SELECT 1 FROM obs.provisioning_resources p JOIN obs.onboarding_workflows w USING(tenant_id) WHERE w.workflow_id=%s AND p.state='uncertain' LIMIT 1",
            (workflow_id,),
        ).fetchone()
        deferred_ready = "awaiting_initial" in states.values() and all(
            n["status"] in {"success", "skipped"}
            for n in nodes
            if n["node_id"].endswith("_provision")
        )
        state = (
            "uncertain"
            if "uncertain" in states.values() or uncertain
            else "failed"
            if "failed" in states.values()
            else "awaiting_initial"
            if deferred_ready
            else "success"
            if all(s in {"success", "skipped"} for s in states.values())
            else "running"
        )
        conn.execute(
            "UPDATE obs.onboarding_workflows SET state=%s,updated_at=now() WHERE workflow_id=%s AND state<>%s",
            (state, workflow_id, state),
        )
        return state


def advance_live(tenant_id: str) -> bool:
    """One bounded coordinator sensor poke; no sleep or worker-slot holding."""
    require_live()
    workflow = one("SELECT * FROM obs.onboarding_workflows WHERE tenant_id=%s", (tenant_id,))
    workflow_id = str(workflow["workflow_id"])
    with connection() as conn:
        nodes = latest(conn, workflow_id)
    for node in nodes:
        if node["node_id"] != "coordinator":
            observe(workflow_id, node)
    with connection() as conn:
        nodes = {n["node_id"]: n for n in latest(conn, workflow_id)}
        payload = conn.execute(
            "SELECT payload FROM obs.onboarding_requests WHERE tenant_id=%s", (tenant_id,)
        ).fetchone()["payload"]
        if any(n["status"] in {"failed", "uncertain"} for n in nodes.values()):
            refresh_needed = True
        else:
            refresh_needed = False
    if refresh_needed:
        state = refresh_state(workflow_id)
        raise RuntimeError(
            f"Onboarding {state}; use the console recovery action after reviewing upstream outcomes."
        )
    for source in ("mysql", "mongo"):
        for phase, dependency in (
            ("provision", None),
            ("initial", "provision"),
            ("cdc", "initial"),
        ):
            node = nodes[f"{source}_{phase}"]
            if node["status"] in {"success", "skipped", "running", "queued"}:
                continue
            if dependency and nodes[f"{source}_{dependency}"]["status"] != "success":
                continue
            if phase == "initial" and not payload["run_initial"]:
                with connection() as conn:
                    update_node(
                        conn,
                        workflow_id,
                        node["node_id"],
                        "awaiting_initial",
                        reason="Initial load deferred by operator; CDC remains blocked.",
                    )
                continue
            trigger_node(workflow_id, node["node_id"])
    state = refresh_state(workflow_id)
    if state == "awaiting_initial":
        # Finish this coordinator run without activating. Resume creates a new
        # coordinator attempt when the operator explicitly starts initial loads.
        return True
    return all(
        n["status"] in {"success", "skipped"} for key, n in nodes.items() if key != "coordinator"
    )


def activate(tenant_id: str, *, actor: str = "airflow:onboarding") -> bool:
    with connection() as conn:
        workflow = conn.execute(
            "SELECT * FROM obs.onboarding_workflows WHERE tenant_id=%s FOR UPDATE", (tenant_id,)
        ).fetchone()
        workflow_id = str(workflow["workflow_id"])
        nodes = latest(conn, workflow_id)
        ready = all(
            n["status"] in {"success", "skipped"} for n in nodes if n["node_id"] != "coordinator"
        )
        isolation = conn.execute(
            """SELECT r.status
                 FROM obs.quality_results r
                 JOIN obs.quality_checks q ON q.id=r.check_id
                WHERE q.tenant_id=%s AND q.kind='tenant_isolation'
                  AND r.checked_at >= (SELECT created_at FROM obs.onboarding_workflows WHERE workflow_id=%s)
                ORDER BY r.checked_at DESC,r.id DESC LIMIT 1""",
            (tenant_id, workflow_id),
        ).fetchone()
        shared_mongo = conn.execute(
            "SELECT coalesce(sources->'mongo'->>'shared','false')='true' AS enabled FROM obs.tenants WHERE tenant_id=%s",
            (tenant_id,),
        ).fetchone()["enabled"]
        if not shared_mongo:
            isolation = {"status": "pass"}
        if ready and shared_mongo and not isolation and settings().mode == "demo":
            check = conn.execute(
                """SELECT id FROM obs.quality_checks
                    WHERE tenant_id=%s AND kind='tenant_isolation' AND enabled
                    ORDER BY id DESC LIMIT 1""",
                (tenant_id,),
            ).fetchone()
            if check:
                conn.execute(
                    """INSERT INTO obs.quality_results(check_id,tenant_id,status,sampled_rows,details,simulated)
                    VALUES(%s,%s,'pass',0,%s,true)""",
                    (
                        check["id"],
                        tenant_id,
                        Jsonb({"foreign_rows": 0, "total_rows": 0, "scope": "demo onboarding isolation gate"}),
                    ),
                )
                isolation = {"status": "pass"}
        if ready and shared_mongo and (not isolation or isolation["status"] != "pass"):
            ready = False
        if ready:
            conn.execute(
                "UPDATE obs.tenants SET status='active',updated_at=now() WHERE tenant_id=%s AND status='onboarding'",
                (tenant_id,),
            )
            audit(conn, actor, "activate_tenant", tenant_id, {"workflow_id": workflow_id})
        task_state(
            conn,
            workflow_id,
            "coordinator",
            "activate_tenant",
            "success" if ready else "blocked",
            error=None if ready else "Tenant isolation check must pass before activation.",
        )
        # Coordinator completion alone never implies initial/CDC completion.
        update_node(conn, workflow_id, "coordinator", "running")
        conn.execute(
            "UPDATE obs.onboarding_workflows SET state=%s,updated_at=now() WHERE workflow_id=%s",
            ("running" if ready else "awaiting_initial", workflow_id),
        )
        notify(
            conn,
            "onboarding.step",
            {
                "tenant_id": tenant_id,
                "step": "activation",
                "status": "success" if ready else "awaiting_initial",
            },
        )
        return ready


def reconcile_live() -> None:
    require_live()
    for workflow in rows(
        "SELECT * FROM obs.onboarding_workflows WHERE state<>'success' ORDER BY updated_at LIMIT 25"
    ):
        workflow_id = str(workflow["workflow_id"])
        try:
            with connection() as conn:
                nodes = latest(conn, workflow_id)
            for node in nodes:
                observe(workflow_id, node)
            refresh_state(workflow_id)
        except Exception as exc:
            with connection() as conn:
                conn.execute(
                    "INSERT INTO obs.collector_state(component,last_error) VALUES(%s,%s) ON CONFLICT(component) DO UPDATE SET last_error=excluded.last_error,updated_at=now()",
                    ("onboarding:" + workflow["tenant_id"], redact(str(exc))[:2000]),
                )


def execution(conf: dict, dag_id: str, run_id: str) -> tuple[dict, dict]:
    """Workers accept only a persisted workflow/run binding, never raw secrets."""
    if set(conf) - {"tenant_id", "workflow_id", "node_id", "attempt"}:
        raise ValueError("DAG conf accepts workflow references only")
    with connection() as conn:
        workflow = conn.execute(
            "SELECT * FROM obs.onboarding_workflows WHERE workflow_id=%s AND tenant_id=%s",
            (conf.get("workflow_id"), conf.get("tenant_id")),
        ).fetchone()
        if not workflow:
            raise ValueError("Unknown onboarding workflow")
        node = next(
            (
                n
                for n in latest(conn, str(workflow["workflow_id"]))
                if n["node_id"] == conf.get("node_id")
            ),
            None,
        )
        if (
            not node
            or node["dag_id"] != dag_id
            or node["dag_run_id"] != run_id
            or node["attempt"] != conf.get("attempt")
        ):
            raise ValueError("DAG run is not the current persisted onboarding attempt")
        payload = conn.execute(
            "SELECT payload FROM obs.onboarding_requests WHERE tenant_id=%s",
            (workflow["tenant_id"],),
        ).fetchone()["payload"]
    return node, payload


def begin_coordinator(conf: dict, dag_id: str, run_id: str) -> None:
    node, _ = execution(conf, dag_id, run_id)
    if node["node_id"] != "coordinator":
        raise ValueError("Expected coordinator node")
    with connection() as conn:
        update_node(
            conn, conf["workflow_id"], "coordinator", "running", started_at=datetime.now(UTC)
        )
        task_state(conn, conf["workflow_id"], "coordinator", "validate_request", "success")
        task_state(conn, conf["workflow_id"], "coordinator", "coordinate_branches", "running")


def resume(tenant_id: str, actor: str, *, start_initial: bool = True) -> dict:
    if settings().mode == "live":
        from obs.actions.live import enabled

        enabled()
    with connection() as conn:
        workflow = conn.execute(
            "SELECT * FROM obs.onboarding_workflows WHERE tenant_id=%s FOR UPDATE", (tenant_id,)
        ).fetchone()
        if not workflow:
            fail(404, "workflow_not_found", "Tracked onboarding workflow not found.")
        if workflow["state"] not in {"failed", "awaiting_initial"}:
            fail(
                409,
                "workflow_not_resumable",
                "Only confirmed failures or deferred initial loads can be resumed.",
            )
        uncertain = conn.execute(
            "SELECT 1 FROM obs.provisioning_resources WHERE tenant_id=%s AND state IN ('creating','uncertain') LIMIT 1",
            (tenant_id,),
        ).fetchone()
        if uncertain:
            fail(
                409,
                "resource_reconciliation_required",
                "Reconcile unconfirmed Airbyte resource creation before resuming.",
            )
        workflow_id = str(workflow["workflow_id"])
        if workflow["state"] == "awaiting_initial" and not start_initial:
            fail(409, "initial_deferred", "Enable initial loads to continue this workflow.")
        if start_initial:
            conn.execute(
                "UPDATE obs.onboarding_requests SET payload=jsonb_set(payload,'{run_initial}','true') WHERE tenant_id=%s",
                (tenant_id,),
            )
        for node in latest(conn, workflow_id):
            if node["node_id"] == "coordinator" or node["status"] == "failed":
                phase = (
                    "coordinator"
                    if node["node_id"] == "coordinator"
                    else node["node_id"].split("_", 1)[1]
                )
                tasks = [
                    {"task_id": key, "label": label, "status": "pending"}
                    for key, label in TASKS[phase]
                ]
                conn.execute(
                    "INSERT INTO obs.onboarding_dag_attempts(workflow_id,node_id,attempt,dag_id,status,tasks) VALUES(%s,%s,%s,%s,%s,%s)",
                    (
                        workflow_id,
                        node["node_id"],
                        node["attempt"] + 1,
                        node["dag_id"],
                        "queued" if node["node_id"] == "coordinator" else "blocked",
                        Jsonb(tasks),
                    ),
                )
            elif node["status"] == "awaiting_initial":
                update_node(
                    conn,
                    workflow_id,
                    node["node_id"],
                    "blocked",
                    reason="Waiting for resumed coordinator",
                )
        conn.execute(
            "UPDATE obs.onboarding_workflows SET state='running',updated_at=now() WHERE workflow_id=%s",
            (workflow_id,),
        )
        if settings().mode == "demo":
            conn.execute(
                "UPDATE obs.demo_jobs SET done=false,step=0,due_at=now(),payload=(SELECT payload FROM obs.onboarding_requests WHERE tenant_id=%s) WHERE job_key=%s",
                (tenant_id, "onboard:" + tenant_id),
            )
        audit(
            conn,
            actor,
            "onboarding.resume",
            tenant_id,
            {"workflow_id": workflow_id, "start_initial": start_initial},
        )
        notify(
            conn, "onboarding.step", {"tenant_id": tenant_id, "step": "resume", "status": "queued"}
        )
    if settings().mode == "live":
        trigger_node(workflow_id, "coordinator")
    return progress(tenant_id)


def demo_tick(conn, job: dict, now: datetime) -> bool:
    """Advance two source branches together; every displayed run is persisted."""
    from obs.demo.scenarios import upsert_run
    from obs.demo.seed import make_run

    tenant, data, step = job["tenant_id"], job["payload"], job["step"]
    workflow_id = str(
        conn.execute(
            "SELECT workflow_id FROM obs.onboarding_workflows WHERE tenant_id=%s", (tenant,)
        ).fetchone()["workflow_id"]
    )

    def start_node(node_id: str) -> dict:
        nodes = {n["node_id"]: n for n in latest(conn, workflow_id)}
        node = nodes[node_id]
        if node["status"] in {"success", "skipped"}:
            return node
        run_id = (
            node["dag_run_id"]
            or f"obs__{workflow_id.replace('-', '')}__{node_id}__a{node['attempt']}"
        )
        conn.execute(
            "UPDATE obs.onboarding_dag_attempts SET dag_run_id=%s,parent_dag_run_id=%s,request_state='confirmed' WHERE workflow_id=%s AND node_id=%s AND attempt=%s",
            (
                run_id,
                None if node_id == "coordinator" else nodes["coordinator"]["dag_run_id"],
                workflow_id,
                node_id,
                node["attempt"],
            ),
        )
        update_node(conn, workflow_id, node_id, "running", started_at=now)
        return {**node, "dag_run_id": run_id}

    def sync_run(source: str, load: str, state: str) -> None:
        node_id = f"{source}_{load}"
        nodes = {n["node_id"]: n for n in latest(conn, workflow_id)}
        node = nodes[node_id]
        if node["status"] == "success":
            return
        if state == "running":
            node = start_node(node_id)
            run = make_run(
                tenant,
                source,
                load,
                now,
                0,
                int(now.timestamp() * 1000) + (source == "mongo") + (100 if load == "cdc" else 0),
                "running",
                "onboarding",
            )
            run.update(
                dag_id=node["dag_id"], dag_run_id=node["dag_run_id"], task_id="sync", map_index=0
            )
            run["run_key"] = f"{node['dag_id']}|{node['dag_run_id']}|sync|0"
            upsert_run(conn, run)
            for key in ("resolve_connections", "sync"):
                task_state(conn, workflow_id, node_id, key, "success")
            task_state(conn, workflow_id, node_id, "wait_for_sync", "running")
        else:
            conn.execute(
                "UPDATE obs.pipeline_runs SET status='success',ended_at=%s,duration_s=greatest(1,extract(epoch FROM %s-started_at)::integer),rows_synced=120000,bytes_synced=19200000 WHERE tenant_id=%s AND dag_id=%s AND dag_run_id=%s",
                (now, now, tenant, node["dag_id"], node["dag_run_id"]),
            )
            task_state(conn, workflow_id, node_id, "wait_for_sync", "success")
            update_node(conn, workflow_id, node_id, "success", ended_at=now)
            notify(conn, "run.updated", {"tenant_id": tenant, "status": "success"})

    coordinator = start_node("coordinator") if step == 0 else None
    if coordinator:
        task_state(conn, workflow_id, "coordinator", "validate_request", "success")
        task_state(conn, workflow_id, "coordinator", "coordinate_branches", "running")
    for source in ("mysql", "mongo"):
        if not data[f"has_{source}"]:
            continue
        if step < 3:
            node_id = source + "_provision"
            node = start_node(node_id)
            if node["status"] != "success":
                task_ids = [key for key, _ in TASKS["provision"]]
                for index, task_id in enumerate(task_ids):
                    task_state(
                        conn,
                        workflow_id,
                        node_id,
                        task_id,
                        "success"
                        if index < (step + 1) * 2
                        else "running"
                        if index == (step + 1) * 2
                        else "pending",
                    )
                if step == 2:
                    mapping = {
                        f"{source}_{load}": f"demo-{tenant}-{source}-{load}"
                        for load in ("initial", "cdc")
                    }
                    conn.execute(
                        "UPDATE obs.tenants SET airbyte_connections=airbyte_connections||%s,updated_at=now() WHERE tenant_id=%s",
                        (Jsonb(mapping), tenant),
                    )
                    for kind in ("source", "initial", "cdc"):
                        conn.execute(
                            "INSERT INTO obs.provisioning_resources(tenant_id,resource_key,remote_id,state) VALUES(%s,%s,%s,'ready') ON CONFLICT DO NOTHING",
                            (tenant, source + ":" + kind, f"demo-{tenant}-{source}-{kind}"),
                        )
                    update_node(conn, workflow_id, node_id, "success", ended_at=now)
        if step == 2:
            if data["run_initial"]:
                sync_run(source, "initial", "running")
            else:
                update_node(
                    conn,
                    workflow_id,
                    source + "_initial",
                    "awaiting_initial",
                    reason="Initial load deferred; source provisioning is complete. CDC remains blocked.",
                )
        elif step == 3 and data["run_initial"]:
            sync_run(source, "initial", "success")
            sync_run(source, "cdc", "running")
        elif step == 4 and data["run_initial"]:
            sync_run(source, "cdc", "success")
    if step == 2 and not data["run_initial"]:
        task_state(conn, workflow_id, "coordinator", "coordinate_branches", "success")
        task_state(conn, workflow_id, "coordinator", "activate_tenant", "blocked")
        update_node(conn, workflow_id, "coordinator", "success", ended_at=now)
        conn.execute(
            "UPDATE obs.onboarding_workflows SET state='awaiting_initial',updated_at=now() WHERE workflow_id=%s",
            (workflow_id,),
        )
        return True
    if step >= 4:
        states = [n["status"] for n in latest(conn, workflow_id) if n["node_id"] != "coordinator"]
        if all(state in {"success", "skipped"} for state in states):
            conn.execute(
                "UPDATE obs.tenants SET status='active',updated_at=now() WHERE tenant_id=%s",
                (tenant,),
            )
            for table in ("customers", "orders", "products", "payments", "events"):
                conn.execute(
                    "INSERT INTO obs.warehouse_snapshots VALUES(%s,%s,24000,%s,%s) ON CONFLICT DO NOTHING",
                    (tenant, table, now, now),
                )
            task_state(conn, workflow_id, "coordinator", "coordinate_branches", "success")
            task_state(conn, workflow_id, "coordinator", "activate_tenant", "success")
            update_node(conn, workflow_id, "coordinator", "success", ended_at=now)
            conn.execute(
                "UPDATE obs.onboarding_workflows SET state='success',updated_at=now() WHERE workflow_id=%s",
                (workflow_id,),
            )
            audit(conn, "demo:onboarding", "activate_tenant", tenant, {"workflow_id": workflow_id})
            notify(
                conn,
                "onboarding.step",
                {"tenant_id": tenant, "step": "activation", "status": "success"},
            )
            return True
    return False
