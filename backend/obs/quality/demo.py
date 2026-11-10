import psycopg
from psycopg.types.json import Jsonb

from obs.quality.engine import execute
from obs.settings import require_demo


def seed_quality(conn: psycopg.Connection) -> None:
    require_demo()
    definitions = [
        (
            "acme_retail",
            "Order amounts present",
            "null_rate",
            {"column": "amount", "max_null_rate": 0.01},
        ),
        (
            "cedar_foods",
            "Order IDs unique in sample",
            "duplicate_keys",
            {"columns": ["id"], "max_duplicate_rate": 0},
        ),
        (
            "bluefin_health",
            "Order IDs in expected set",
            "accepted_values",
            {"column": "id", "values": [str(i) for i in range(100)], "max_invalid_rate": 0},
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
        ),
    ]
    for tenant_id, name, kind, params in definitions:
        if not conn.execute(
            "SELECT 1 FROM obs.tenants WHERE tenant_id=%s", (tenant_id,)
        ).fetchone():
            continue
        item = conn.execute(
            """INSERT INTO obs.quality_checks(tenant_id,name,table_name,kind,params,sample_limit)
            VALUES(%s,%s,'orders',%s,%s,100) ON CONFLICT(tenant_id,name) DO NOTHING RETURNING *""",
            (tenant_id, name, kind, Jsonb(params)),
        ).fetchone()
        if item:
            execute(conn, item)
