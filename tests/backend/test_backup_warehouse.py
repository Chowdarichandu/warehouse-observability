from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
import pytest

from obs.backup import dump, restore
from obs.db import connection, one
from obs.integrations import warehouse
from obs.settings import settings


def test_catalog_adapter_records_estimates_freshness_and_schema(monkeypatch):
    schema = "test_catalog_" + uuid4().hex[:12]
    with connection() as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        conn.execute(
            sql.SQL(
                "CREATE TABLE {}.orders(id bigint, _airbyte_extracted_at timestamptz)"
            ).format(sql.Identifier(schema))
        )
        conn.execute(
            sql.SQL("INSERT INTO {}.orders VALUES(1,now()),(2,now())").format(
                sql.Identifier(schema)
            )
        )
        conn.execute(sql.SQL("ANALYZE {}.orders").format(sql.Identifier(schema)))
    monkeypatch.setattr(
        warehouse,
        "connect",
        lambda: psycopg.connect(settings().database_url, row_factory=dict_row),
    )
    try:
        with connection() as conn:
            warehouse.collect(
                conn, {"tenant_id": "test_catalog", "warehouse_schema": schema}
            )
        snapshot = one(
            "SELECT * FROM obs.warehouse_snapshots WHERE tenant_id='test_catalog' ORDER BY checked_at DESC LIMIT 1"
        )
        assert snapshot["row_count"] == 2 and snapshot["last_loaded_at"] is not None
        columns = one(
            "SELECT columns FROM obs.schema_snapshots WHERE tenant_id='test_catalog' ORDER BY checked_at DESC LIMIT 1"
        )["columns"]
        assert [c["name"] for c in columns] == ["id", "_airbyte_extracted_at"]
    finally:
        with connection() as conn:
            conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
            conn.execute(
                "DELETE FROM obs.warehouse_snapshots WHERE tenant_id='test_catalog'"
            )
            conn.execute(
                "DELETE FROM obs.schema_snapshots WHERE tenant_id='test_catalog'"
            )


def test_real_pg_dump_restore_roundtrip_to_isolated_empty_database(tmp_path: Path):
    database = "obs_restore_" + uuid4().hex[:12]
    params = conninfo_to_dict(settings().database_url)
    target = make_conninfo(**(params | {"dbname": database}))
    archive = tmp_path / "console.dump"
    expected = one("SELECT count(*) AS n FROM obs.tenants")["n"]
    dump(settings().database_url, archive)
    assert archive.stat().st_size > 0 and archive.stat().st_mode & 0o777 == 0o600
    with pytest.raises(RuntimeError, match="empty"):
        restore(settings().database_url, archive)
    with psycopg.connect(settings().database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            restore(target, archive)
            with psycopg.connect(target) as restored:
                assert (
                    restored.execute("SELECT count(*) FROM obs.tenants").fetchone()[0]
                    == expected
                )
                assert (
                    restored.execute(
                        "SELECT count(*) FROM obs.schema_migrations"
                    ).fetchone()[0]
                    >= 6
                )
        finally:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    sql.Identifier(database)
                )
            )
