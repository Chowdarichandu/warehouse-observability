import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from obs.settings import require_live, settings

POSTGRES_TABLES = """SELECT c.relname AS table_name,
CASE WHEN c.reltuples < 0 THEN NULL ELSE c.reltuples::bigint END AS row_count
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname=%s AND c.relkind IN ('r','p') ORDER BY c.relname"""
# Empty Redshift tables are absent from SVV_TABLE_INFO: keep them as unknown, not a false zero.
REDSHIFT_TABLES = """SELECT t.table_name, s.estimated_visible_rows::bigint AS row_count
FROM information_schema.tables t LEFT JOIN svv_table_info s
ON s.schema=t.table_schema AND s.table=t.table_name
WHERE t.table_schema=%s AND t.table_type='BASE TABLE' ORDER BY t.table_name"""


def connect() -> psycopg.Connection[dict[str, Any]]:
    require_live()
    if "sslmode=verify-full" not in settings().warehouse_url:
        raise ValueError("WAREHOUSE_URL must use sslmode=verify-full")
    return psycopg.connect(
        settings().warehouse_url,
        connect_timeout=5,
        row_factory=dict_row,
        options=f"-c statement_timeout={settings().warehouse_statement_timeout_ms}",
    )


def collect(conn: psycopg.Connection[dict[str, Any]], tenant: dict[str, Any]) -> None:
    schema = tenant.get("warehouse_schema")
    if not schema:
        return
    now = datetime.now(UTC)
    with connect() as warehouse:
        warehouse.execute("SET TRANSACTION READ ONLY")
        tables = warehouse.execute(
            REDSHIFT_TABLES if settings().warehouse_engine == "redshift" else POSTGRES_TABLES,
            (schema,),
        ).fetchall()
        for table in tables:
            columns = warehouse.execute(
                """SELECT column_name AS name,data_type AS type FROM information_schema.columns
                WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position""",
                (schema, table["table_name"]),
            ).fetchall()
            load_column = settings().warehouse_load_column
            loaded = None
            if any(c["name"] == load_column for c in columns):
                # Bounded by server-side timeout; use a timestamp index/sort key in the destination.
                loaded = warehouse.execute(
                    sql.SQL("SELECT max({}) AS loaded FROM {}.{}").format(
                        sql.Identifier(load_column),
                        sql.Identifier(schema),
                        sql.Identifier(table["table_name"]),
                    )
                ).fetchone()["loaded"]
            conn.execute(
                """INSERT INTO obs.warehouse_snapshots(tenant_id,table_name,row_count,last_loaded_at,checked_at)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (tenant["tenant_id"], table["table_name"], table["row_count"], loaded, now),
            )
            digest = hashlib.sha256(json.dumps(columns, sort_keys=True).encode()).hexdigest()
            conn.execute(
                """INSERT INTO obs.schema_snapshots(tenant_id,table_name,columns,columns_hash,checked_at)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (tenant["tenant_id"], table["table_name"], Jsonb(columns), digest, now),
            )
