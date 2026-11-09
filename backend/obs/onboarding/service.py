from psycopg.types.json import Jsonb

from obs.api.schemas import OnboardInput
from obs.audit import audit
from obs.auth import fail
from obs.db import connection, notify
from obs.onboarding.preflight import preflight
from obs.settings import require_demo

STEPS = [
    "Create sources",
    "Check connections",
    "Create initial and CDC connections",
    "Save connection IDs",
    "Run initial loads",
    "Activate tenant",
]


def start(data: OnboardInput, actor: str) -> dict:
    require_demo()
    preflight(data)
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
        conn.execute(
            "INSERT INTO obs.demo_jobs(job_key,kind,tenant_id,payload) VALUES(%s,'onboarding',%s,%s)",
            (f"onboard:{data.tenant_id}", data.tenant_id, Jsonb(payload)),
        )
        conn.execute(
            "INSERT INTO obs.tenant_events(tenant_id,step,status,message) VALUES(%s,%s,'started','Simulated workflow queued')",
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
                "simulated": True,
            },
        )
        notify(
            conn,
            "onboarding.step",
            {"tenant_id": data.tenant_id, "step": STEPS[0], "status": "started"},
        )
    return {"tenant_id": data.tenant_id, "status": "onboarding", "events": []}
