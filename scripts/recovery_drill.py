"""Restore a synthetic console database into a newly created isolated database."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from obs.backup import dump, restore


def validate_admin_dsn(dsn: str) -> dict[str, str]:
    values = conninfo_to_dict(dsn)
    if values.get("host") not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(
            "Recovery drills only accept an explicitly configured loopback PostgreSQL"
        )
    if not values.get("dbname"):
        raise ValueError("An admin database must be explicit")
    if values.get("service") or values.get("hostaddr") not in {
        None,
        "127.0.0.1",
        "::1",
    }:
        raise ValueError(
            "Recovery drills reject service indirection and remote host addresses"
        )
    # Explicit hostaddr prevents PGHOSTADDR/PGSERVICE defaults and localhost DNS
    # overrides from redirecting a drill to a remote database.
    values["hostaddr"] = "::1" if values["host"] == "::1" else "127.0.0.1"
    return values


def snapshot(dsn: str) -> dict[str, str]:
    """Content fingerprints of every application table, including migrations and empty tables."""
    result = {}
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        conn.execute("SET TIME ZONE 'UTC'")
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='obs' ORDER BY tablename"
        ).fetchall()
        for (table,) in tables:
            rows = conn.execute(
                sql.SQL(
                    "SELECT row_to_json(t)::text FROM obs.{} t ORDER BY row_to_json(t)::text"
                ).format(sql.Identifier(table))
            ).fetchall()
            digest = hashlib.sha256()
            for (row,) in rows:
                digest.update(row.encode())
                digest.update(b"\n")
            result[table] = digest.hexdigest()
    return result


def drill(admin_dsn: str) -> dict:
    params = validate_admin_dsn(admin_dsn)
    admin_dsn = make_conninfo(**params)
    prefix = "obs_drill_" + uuid4().hex[:16]
    source_name, target_name = prefix + "_source", prefix + "_target"
    source = make_conninfo(**(params | {"dbname": source_name}))
    target = make_conninfo(**(params | {"dbname": target_name}))
    created = []
    with psycopg.connect(admin_dsn, autocommit=True, connect_timeout=5) as admin:
        try:
            for name in (source_name, target_name):
                admin.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name))
                )
                created.append(name)
            environment = dict(os.environ, DATABASE_URL=source, MODE="demo")
            # No AWS bootstrap or demo ticker is involved; only this new scratch DB is migrated.
            migration = subprocess.run(
                [sys.executable, "-m", "obs.migrate"],
                env=environment,
                capture_output=True,
                timeout=90,
            )
            if migration.returncode:
                raise RuntimeError("Synthetic database migration failed")
            with psycopg.connect(source, connect_timeout=5) as conn:
                conn.execute(
                    "INSERT INTO obs.tenants(tenant_id,display_name,status,airbyte_connections) "
                    "VALUES ('restore_fixture','Recovery fixture ✓','active',"
                    '\'{"mysql_cdc":"fixture-connection"}\')'
                )
                conn.execute(
                    "INSERT INTO obs.pipeline_runs(run_key,tenant_id,source_type,load_type,status,"
                    "rows_synced,duration_s) VALUES ('drill|run','restore_fixture','mysql','cdc',"
                    "'success',12345,42)"
                )
                conn.execute(
                    "INSERT INTO obs.run_logs(run_key,source,content) "
                    "VALUES ('drill|run','airflow','Synthetic log ✓ token=[REDACTED]')"
                )
                fixture_user = conn.execute(
                    "INSERT INTO obs.users(email,display_name,role) "
                    "VALUES ('fixture@restore.local','Recovery fixture','viewer') RETURNING user_id"
                ).fetchone()[0]
            expected = snapshot(source)
            with tempfile.TemporaryDirectory(prefix="obs-recovery-drill-") as directory:
                archive = Path(directory) / "fixture.dump"
                dump(source, archive)
                restore(target, archive)
                actual = snapshot(target)
                if actual != expected or not actual:
                    raise RuntimeError(
                        "Restored table content differs from the source fixture"
                    )
                with psycopg.connect(target, connect_timeout=5) as conn:
                    next_user = conn.execute(
                        "INSERT INTO obs.users(email,display_name,role) "
                        "VALUES ('next@restore.local','Sequence verification','viewer') RETURNING user_id"
                    ).fetchone()[0]
                    if next_user != fixture_user + 1:
                        raise RuntimeError(
                            "Restored sequence state differs from the source"
                        )
                # Verify the guard against accidentally restoring over a running application.
                try:
                    restore(target, archive)
                except RuntimeError as exc:
                    if "empty" not in str(exc):
                        raise
                else:
                    raise RuntimeError("Nonempty restore target was not rejected")
                archive_bytes = archive.stat().st_size
            return {
                "passed": True,
                "fixture": "synthetic migrations + tenant/run/redacted log",
                "tables_compared": len(actual),
                "archive_bytes": archive_bytes,
                "nonempty_target_rejected": True,
                "sequence_state_verified": True,
                "production_data_accessed": False,
            }
        finally:
            # Only names generated and successfully created by this invocation can be dropped.
            for name in reversed(created):
                admin.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(name)
                    )
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-isolated", action="store_true")
    args = parser.parse_args()
    if not args.confirm_isolated or not os.getenv("OBS_DRILL_ADMIN_DSN"):
        parser.exit(
            2,
            "Set OBS_DRILL_ADMIN_DSN for an isolated local server and --confirm-isolated.\n",
        )
    try:
        print(json.dumps(drill(os.environ["OBS_DRILL_ADMIN_DSN"]), indent=2))
    except (
        ValueError,
        RuntimeError,
        psycopg.Error,
        OSError,
        subprocess.SubprocessError,
    ):
        parser.exit(
            1,
            "Recovery drill failed. Check isolated PostgreSQL permissions and client tools.\n",
        )


if __name__ == "__main__":
    main()
