from psycopg.types.json import Jsonb

from obs.api.schemas import OnboardInput
from obs.audit import audit
from obs.auth import fail
from obs.db import connection, notify
from obs.onboarding import workflow
from obs.onboarding.preflight import preflight
from obs.settings import settings

# Legacy event labels remain readable; workflow DAG/task state is authoritative.
STEPS = [
    "Validate onboarding request",
    "Create tenant record",
    "Create warehouse schema",
    "Create Airbyte connections",
    "Create dedicated MySQL database",
    "Provision MySQL user and grants",
    "Register shared MongoDB cluster",
    "Configure tenant document key",
    "Begin initial load (MySQL)",
    "Snapshot tables to warehouse",
    "Verify row counts",
    "Begin initial load (MongoDB)",
    "Snapshot collections to warehouse",
    "Verify document counts",
    "Enable binlog CDC",
    "Start MySQL CDC sync",
    "Enable change-stream CDC",
    "Start MongoDB CDC sync",
    "Activate tenant",
]

# Which source each step belongs to; None means the step always runs.
STEP_SOURCE = {
    "Create dedicated MySQL database": "mysql",
    "Provision MySQL user and grants": "mysql",
    "Register shared MongoDB cluster": "mongo",
    "Configure tenant document key": "mongo",
    "Begin initial load (MySQL)": "mysql",
    "Snapshot tables to warehouse": "mysql",
    "Verify row counts": "mysql",
    "Begin initial load (MongoDB)": "mongo",
    "Snapshot collections to warehouse": "mongo",
    "Verify document counts": "mongo",
    "Enable binlog CDC": "mysql",
    "Start MySQL CDC sync": "mysql",
    "Enable change-stream CDC": "mongo",
    "Start MongoDB CDC sync": "mongo",
}


def plan_for(data: dict) -> list:
    """The ordered onboarding steps for one tenant, filtered by its sources.

    Onboarding runs seven DAGs in sequence (onboarding, per-source
    provisioning, per-source initial load, per-source CDC); this is the flat
    step list those DAGs emit events for.
    """
    return [
        step
        for step in STEPS
        if STEP_SOURCE.get(step) is None or data.get(f"has_{STEP_SOURCE[step]}")
    ]


def start(data: OnboardInput, actor: str) -> dict:
    live = settings().mode == "live"
    if live:
        fail(
            503,
            "onboarding_validation_required",
            "Live onboarding is unavailable until tenant isolation and DAG recovery are validated in staging.",
        )
        from obs.actions.live import enabled

        enabled()
        if not settings().registry_dags_enabled:
            fail(
                409,
                "registry_not_enabled",
                "Deploy and enable the reviewed onboarding DAGs before onboarding.",
            )
    if not preflight(data)["passed"]:
        fail(422, "preflight_failed", "Preflight checks must pass before onboarding.")
    with connection() as conn:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("onboard:" + data.tenant_id,)
        )
        existing = conn.execute(
            "SELECT status FROM obs.tenants WHERE tenant_id=%s", (data.tenant_id,)
        ).fetchone()
        old = conn.execute(
            "SELECT payload FROM obs.onboarding_requests WHERE tenant_id=%s", (data.tenant_id,)
        ).fetchone()
        if existing:
            if not old or old["payload"] != data.model_dump():
                fail(
                    409,
                    "tenant_exists",
                    "This tenant slug is already registered with a different configuration.",
                )
            workflow_id = None
        else:
            conn.execute(
                """INSERT INTO obs.tenants(
                    tenant_id,display_name,status,has_mysql,has_mongo,sources,
                    warehouse_schema,freshness_sla_min,owner_email
                ) VALUES(%s,%s,'onboarding',%s,%s,%s,%s,%s,%s)""",
                (
                    data.tenant_id,
                    data.display_name,
                    data.has_mysql,
                    data.has_mongo,
                    Jsonb(
                        {
                            **(
                                {
                                    "mysql": {
                                        "database": data.mysql_database,
                                        "database_per_tenant": True,
                                    }
                                }
                                if data.has_mysql
                                else {}
                            ),
                            **(
                                {
                                    "mongo": {
                                        "database": data.mongo_database,
                                        "shared": True,
                                        "tenant_field": "tenant_id",
                                    }
                                }
                                if data.has_mongo
                                else {}
                            ),
                        }
                    ),
                    data.warehouse_schema or data.tenant_id,
                    data.freshness_sla_min,
                    data.owner_email,
                ),
            )
            conn.execute(
                "INSERT INTO obs.onboarding_requests(tenant_id,payload) VALUES(%s,%s)",
                (data.tenant_id, Jsonb(data.model_dump())),
            )
            workflow_id = workflow.initialize(conn, data)
            if not live and data.has_mongo:
                conn.execute(
                    """INSERT INTO obs.quality_checks(tenant_id,name,table_name,kind,params,sample_limit)
                    VALUES(%s,'Tenant isolation','orders','tenant_isolation',%s,100)
                    ON CONFLICT(tenant_id,name) DO UPDATE SET enabled=true
                    RETURNING id""",
                    (data.tenant_id, Jsonb({"tenant_field": "tenant_id"})),
                ).fetchone()
                conn.execute(
                    "INSERT INTO obs.demo_jobs(job_key,kind,tenant_id,payload) VALUES(%s,'onboarding',%s,%s)",
                    (f"onboard:{data.tenant_id}", data.tenant_id, Jsonb(data.model_dump())),
                )
            conn.execute(
                "INSERT INTO obs.tenant_events(tenant_id,step,status,message) VALUES(%s,'Coordinator','started','Seven-DAG onboarding requested')",
                (data.tenant_id,),
            )
            audit(
                conn,
                actor,
                "onboard_tenant",
                data.tenant_id,
                {"simulated": not live, "workflow_id": workflow_id},
            )
            notify(
                conn,
                "onboarding.step",
                {"tenant_id": data.tenant_id, "step": "coordinator", "status": "queued"},
            )
    if live and workflow_id:
        workflow.trigger_node(workflow_id, "coordinator")
    return workflow.progress(data.tenant_id)


def start_live(data: OnboardInput, actor: str) -> dict:
    return start(data, actor)
