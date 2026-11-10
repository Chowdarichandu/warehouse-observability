from psycopg.types.json import Jsonb

from obs.api.schemas import OnboardInput
from obs.audit import audit
from obs.auth import fail
from obs.db import connection, notify
from obs.onboarding.preflight import preflight
from obs.settings import settings

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
        return start_live(data, actor)
    result = preflight(data)
    if not result["passed"]:
        fail(422, "preflight_failed", "Preflight checks must pass before onboarding.")
    with connection() as conn:
        if conn.execute(
            "SELECT 1 FROM obs.tenants WHERE tenant_id=%s", (data.tenant_id,)
        ).fetchone():
            fail(409, "tenant_exists", "This tenant slug is already registered.")
        conn.execute(
            """INSERT INTO obs.tenants(tenant_id,display_name,status,has_mysql,has_mongo,warehouse_schema,freshness_sla_min,owner_email)
            VALUES(%s,%s,'onboarding',%s,%s,%s,%s,%s)""",
            (
                data.tenant_id,
                data.display_name,
                data.has_mysql,
                data.has_mongo,
                data.warehouse_schema or data.tenant_id,
                data.freshness_sla_min,
                data.owner_email,
            ),
        )
        # Store references, never a password or a raw connection string.
        payload = data.model_dump()
        if not live:
            conn.execute(
                "INSERT INTO obs.demo_jobs(job_key,kind,tenant_id,payload) VALUES(%s,'onboarding',%s,%s)",
                (f"onboard:{data.tenant_id}", data.tenant_id, Jsonb(payload)),
            )
        conn.execute(
            "INSERT INTO obs.tenant_events(tenant_id,step,status,message) VALUES(%s,%s,'started','Onboarding requested')",
            (data.tenant_id, STEPS[0]),
        )
        audit(
            conn,
            actor,
            "onboard_tenant",
            data.tenant_id,
            {
                "sources": [
                    s for s, on in [("mysql", data.has_mysql), ("mongo", data.has_mongo)] if on
                ],
                "simulated": not live,
            },
        )
        notify(
            conn,
            "onboarding.step",
            {"tenant_id": data.tenant_id, "step": STEPS[0], "status": "started"},
        )
    return {"tenant_id": data.tenant_id, "status": "onboarding", "events": []}


def start_live(data: OnboardInput, actor: str) -> dict:
    from obs.actions.live import enabled, execute

    enabled()
    if not settings().registry_dags_enabled:
        fail(
            409,
            "registry_not_enabled",
            "Deploy and enable the registry-driven DAGs before onboarding.",
        )
    result = preflight(data)
    if not result["passed"]:
        fail(422, "preflight_failed", "Preflight checks must pass before onboarding.")
    with connection() as conn:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("onboard:" + data.tenant_id,)
        )
        existing = conn.execute(
            "SELECT * FROM obs.tenants WHERE tenant_id=%s", (data.tenant_id,)
        ).fetchone()
        request = conn.execute(
            "SELECT payload FROM obs.onboarding_requests WHERE tenant_id=%s", (data.tenant_id,)
        ).fetchone()
        if existing:
            if (
                existing["status"] != "onboarding"
                or not request
                or request["payload"] != data.model_dump()
            ):
                fail(
                    409,
                    "tenant_exists",
                    "Tenant already exists with a different configuration or completed onboarding.",
                )
        else:
            conn.execute(
                """INSERT INTO obs.tenants(tenant_id,display_name,status,has_mysql,has_mongo,warehouse_schema,freshness_sla_min,owner_email)
                VALUES(%s,%s,'onboarding',%s,%s,%s,%s,%s)""",
                (
                    data.tenant_id,
                    data.display_name,
                    data.has_mysql,
                    data.has_mongo,
                    data.warehouse_schema or data.tenant_id,
                    data.freshness_sla_min,
                    data.owner_email,
                ),
            )
            conn.execute(
                "INSERT INTO obs.onboarding_requests(tenant_id,payload) VALUES(%s,%s)",
                (data.tenant_id, Jsonb(data.model_dump())),
            )
            audit(conn, actor, "onboard_tenant", data.tenant_id, {"simulated": False})
            notify(
                conn,
                "onboarding.step",
                {"tenant_id": data.tenant_id, "step": "Requested", "status": "started"},
            )
    execute("onboard", data.tenant_id, actor, data.model_dump(), f"onboard:{data.tenant_id}")
    return {"tenant_id": data.tenant_id, "status": "onboarding", "events": []}
