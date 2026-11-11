import psycopg
from psycopg.types.json import Jsonb

from obs.quality.engine import execute
from obs.settings import require_demo


def seed_quality(conn: psycopg.Connection) -> None:
    require_demo()
    # Each definition names a table that exists in that tenant's catalog.
    definitions = [
        (
            "__all__",
            "Tenant isolation",
            "tenant_isolation",
            {"tenant_field": "tenant_id"},
            None,  # Resolved per tenant from its catalog below.
        ),
        (
            "acme_retail",
            "Order amounts present",
            "null_rate",
            {"column": "amount", "max_null_rate": 0.01},
            "orders",
        ),
        (
            "cedar_foods",
            "Order IDs unique in sample",
            "duplicate_keys",
            {"columns": ["id"], "max_duplicate_rate": 0},
            "orders",
        ),
        (
            "bluefin_health",
            "Appointment IDs in expected set",
            "accepted_values",
            {"column": "id", "values": [str(i) for i in range(100)], "max_invalid_rate": 0},
            "appointments",
        ),
        (
            "orbit_logistics",
            "Orders schema contract",
            "schema_contract",
            {
                "columns": {
                    "id": "bigint",
                    "created_at": "timestamp",
                    "amount": "numeric",
                },
                "allow_extra": False,
            },
            "orders",
        ),
    ]
    for tenant_id, name, kind, params, table_name in definitions:
        tenant_ids = (
            [
                row["tenant_id"]
                for row in conn.execute(
                    "SELECT tenant_id FROM obs.tenants WHERE sources->'mongo'->>'shared'='true'"
                ).fetchall()
            ]
            if tenant_id == "__all__"
            else [tenant_id]
        )
        for current_tenant in tenant_ids:
            table = table_name or _first_catalog_table(conn, current_tenant)
            if table is None:
                continue
            item = conn.execute(
                """INSERT INTO obs.quality_checks(tenant_id,name,table_name,kind,params,sample_limit)
                VALUES(%s,%s,%s,%s,%s,100) ON CONFLICT(tenant_id,name) DO NOTHING RETURNING *""",
                (current_tenant, name, table, kind, Jsonb(params)),
            ).fetchone()
            if item:
                execute(conn, item)
    _seed_pinecrest_history(conn)


def _first_catalog_table(conn: psycopg.Connection, tenant_id: str) -> str | None:
    row = conn.execute(
        "SELECT table_name FROM obs.schema_snapshots WHERE tenant_id=%s ORDER BY table_name LIMIT 1",
        (tenant_id,),
    ).fetchone()
    return row["table_name"] if row else None


def _seed_pinecrest_history(conn: psycopg.Connection) -> None:
    """SPEC §13: pinecrest_edu has a resolved tenant-isolation incident from
    3 days ago, with its quality check history. The latest result is a pass,
    so the alerter stays quiet and the incident stays resolved."""
    check = conn.execute(
        "SELECT id FROM obs.quality_checks WHERE tenant_id='pinecrest_edu' AND kind='tenant_isolation'"
    ).fetchone()
    if not check:
        return
    existing = conn.execute(
        "SELECT 1 FROM obs.incidents WHERE tenant_id='pinecrest_edu' AND cause_rule='tenant_isolation'"
    ).fetchone()
    if existing:
        return
    conn.execute(
        """INSERT INTO obs.quality_results(check_id,tenant_id,status,sampled_rows,details,simulated,checked_at)
           VALUES(%s,'pinecrest_edu','fail',100,%s,true,now()-interval '3 days')""",
        (check["id"], Jsonb({"foreign_rows": 14, "total_rows": 100})),
    )
    conn.execute(
        """INSERT INTO obs.quality_results(check_id,tenant_id,status,sampled_rows,details,simulated,checked_at)
           VALUES(%s,'pinecrest_edu','pass',100,%s,true,now()-interval '2 days')""",
        (check["id"], Jsonb({"foreign_rows": 0, "total_rows": 100})),
    )
    incident = conn.execute(
        """INSERT INTO obs.incidents(tenant_id,source_type,severity,state,title,cause_rule,
              opened_at,acknowledged_by,acknowledged_at,assignee,resolved_by,resolved_at,root_cause_category)
           VALUES('pinecrest_edu','mongo','critical','resolved','Tenant isolation check failed',
              'tenant_isolation',now()-interval '3 days','operator@demo.local',
              now()-interval '3 days'+interval '3 hours','operator@demo.local',
              'operator@demo.local',now()-interval '2 days','Configuration')
           RETURNING id""",
    ).fetchone()
    conn.execute(
        """INSERT INTO obs.alerts(rule_id,fingerprint,tenant_id,severity,state,title,details,
              first_fired_at,last_seen_at,acked_by,acked_at,resolved_at,incident_id)
           VALUES('tenant_isolation','tenant_isolation|pinecrest_edu|mongo','pinecrest_edu',
              'critical','resolved','Tenant isolation breach · pinecrest_edu',%s,
              now()-interval '3 days',now()-interval '2 days','operator@demo.local',
              now()-interval '3 days'+interval '3 hours',now()-interval '2 days',%s)""",
        (Jsonb({"foreign_rows": 14, "total_rows": 100}), incident["id"]),
    )
