"""Read-only adapters for the supported warehouse engines."""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Protocol

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from obs.settings import require_live, settings

POSTGRES_TABLES = """SELECT c.relname AS table_name,
CASE WHEN c.reltuples < 0 THEN NULL ELSE c.reltuples::bigint END AS row_count
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname=%s AND c.relkind IN ('r','p') ORDER BY c.relname"""
REDSHIFT_TABLES = """SELECT t.table_name, s.estimated_visible_rows::bigint AS row_count
FROM information_schema.tables t LEFT JOIN svv_table_info s
ON s.schema=t.table_schema AND s.table=t.table_name
WHERE t.table_schema=%s AND t.table_type='BASE TABLE' ORDER BY t.table_name"""
SNOWFLAKE_TABLES = """SELECT table_name, row_count FROM information_schema.tables
WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name"""


class Result(Protocol):
    def fetchall(self) -> list[dict[str, Any]]: ...
    def fetchone(self) -> dict[str, Any] | None: ...


class WarehouseConnection(Protocol):
    def __enter__(self) -> "WarehouseConnection": ...
    def __exit__(self, *args: object) -> None: ...
    def execute(self, query: Any, params: tuple[Any, ...] = ()) -> Result: ...


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


def _query_text(query: Any) -> str:
    if isinstance(query, str):
        return query
    if hasattr(query, "as_string"):
        return query.as_string(None)
    return str(query)


class _SnowflakeConnection:
    def __init__(self, connection: Any):
        self.connection = connection

    def __enter__(self) -> "_SnowflakeConnection":
        return self

    def __exit__(self, *args: object) -> None:
        self.connection.close()

    def execute(self, query: Any, params: tuple[Any, ...] = ()) -> _Rows:
        cursor = self.connection.cursor()
        cursor.execute(_query_text(query), params)
        names = [column[0].lower() for column in (cursor.description or ())]
        return _Rows([dict(zip(names, row, strict=False)) for row in cursor.fetchall()])


class _BigQueryConnection:
    def __init__(self, client: Any):
        self.client = client

    def __enter__(self) -> "_BigQueryConnection":
        return self

    def __exit__(self, *args: object) -> None:
        close = getattr(self.client, "close", None)
        if close:
            close()

    def execute(self, query: Any, params: tuple[Any, ...] = ()) -> _Rows:
        from google.cloud import bigquery  # type: ignore[import-not-found]

        text = _query_text(query).replace('"', "`")
        if "FROM information_schema.columns" in text.lower():
            text = text.replace(
                "information_schema.columns",
                f"`{settings().warehouse_project}.{settings().warehouse_dataset}.INFORMATION_SCHEMA.COLUMNS`",
            )
        index = 0

        def replacement(_: re.Match[str]) -> str:
            nonlocal index
            name = f"p{index}"
            index += 1
            return f"@{name}"

        text = re.sub(r"%s", replacement, text)
        query_params = []
        for index, value in enumerate(params):
            if isinstance(value, bool):
                kind = "BOOL"
            elif isinstance(value, int):
                kind = "INT64"
            elif isinstance(value, float):
                kind = "FLOAT64"
            elif isinstance(value, datetime):
                kind = "TIMESTAMP"
            else:
                kind = "STRING"
            query_params.append(bigquery.ScalarQueryParameter(f"p{index}", kind, value))
        config = bigquery.QueryJobConfig(query_parameters=query_params, use_query_cache=True)
        rows = self.client.query(text, job_config=config).result()
        return _Rows([dict(row.items()) for row in rows])


def _snowflake_connect() -> _SnowflakeConnection:
    try:
        import snowflake.connector  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "WAREHOUSE_ENGINE=snowflake requires snowflake-connector-python"
        ) from exc
    config = settings()
    if not config.warehouse_account or not config.warehouse_user:
        raise ValueError("Snowflake requires WAREHOUSE_ACCOUNT and WAREHOUSE_USER")
    connection = snowflake.connector.connect(
        account=config.warehouse_account,
        user=config.warehouse_user,
        password=config.warehouse_password,
        database=config.warehouse_database or None,
        schema=config.warehouse_dataset or None,
        warehouse=config.warehouse_name or None,
        role=config.warehouse_role or None,
        session_parameters={"QUERY_TAG": "pravah-read-only"},
    )
    connection.cursor().execute("ALTER SESSION SET TRANSACTION_ABORT_ON_ERROR=TRUE")
    return _SnowflakeConnection(connection)


def _bigquery_connect() -> _BigQueryConnection:
    try:
        from google.cloud import bigquery  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("WAREHOUSE_ENGINE=bigquery requires google-cloud-bigquery") from exc
    config = settings()
    if not config.warehouse_project or not config.warehouse_dataset:
        raise ValueError("BigQuery requires WAREHOUSE_PROJECT and WAREHOUSE_DATASET")
    return _BigQueryConnection(bigquery.Client(project=config.warehouse_project))


def connect() -> WarehouseConnection:
    require_live()
    config = settings()
    if config.warehouse_engine == "snowflake":
        return _snowflake_connect()
    if config.warehouse_engine == "bigquery":
        return _bigquery_connect()
    if "sslmode=verify-full" not in config.warehouse_url:
        raise ValueError("WAREHOUSE_URL must use sslmode=verify-full")
    return psycopg.connect(
        config.warehouse_url,
        connect_timeout=5,
        row_factory=dict_row,
        options=f"-c statement_timeout={config.warehouse_statement_timeout_ms}",
    )


def _tables_query() -> str:
    engine = settings().warehouse_engine
    if engine == "redshift":
        return REDSHIFT_TABLES
    if engine == "snowflake":
        return SNOWFLAKE_TABLES
    if engine == "bigquery":
        return (
            f"SELECT table_name, total_rows AS row_count FROM "
            f"`{settings().warehouse_project}.{settings().warehouse_dataset}.INFORMATION_SCHEMA.TABLE_STORAGE` "
            "WHERE table_type='BASE TABLE' ORDER BY table_name"
        )
    return POSTGRES_TABLES


def _columns_query() -> str:
    return """SELECT column_name AS name,data_type AS type FROM information_schema.columns
    WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position"""


def collect(conn: psycopg.Connection[dict[str, Any]], tenant: dict[str, Any]) -> None:
    schema = tenant.get("warehouse_schema")
    if not schema:
        return
    now = datetime.now(UTC)
    config = settings()
    with connect() as warehouse:
        if config.warehouse_engine in {"postgres", "redshift"}:
            warehouse.execute("SET TRANSACTION READ ONLY")
        table_params = () if config.warehouse_engine == "bigquery" else (schema,)
        tables = warehouse.execute(_tables_query(), table_params).fetchall()
        for table in tables:
            columns = warehouse.execute(_columns_query(), (schema, table["table_name"])).fetchall()
            load_column = config.warehouse_load_column
            loaded = None
            if any(column["name"] == load_column for column in columns):
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
