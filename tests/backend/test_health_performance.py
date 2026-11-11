from pathlib import Path
from uuid import uuid4

from obs.db import connection


def test_set_based_health_preserves_original_semantics() -> None:
    """Compare the optimized view with the original for isolated edge cases."""
    migration = Path(__file__).resolve().parents[2] / "sql/migrations/004_views.sql"
    original = (
        migration.read_text()
        .split("CREATE VIEW obs.v_tenant_health AS\n", 1)[1]
        .rstrip(";\n")
    )
    prefix = "health_regression_" + uuid4().hex[:8]
    cases = {
        "no_sources": "healthy",
        "never_succeeded": "down",
        "paused": "paused",
        "healthy": "healthy",
        "warning": "degraded",
        "recent_failure": "degraded",
        "failed_cdc": "down",
        "stuck": "degraded",
        "queued_after_failed": "down",
    }
    with connection() as conn:
        try:
            for name in cases:
                tenant = f"{prefix}_{name}"
                conn.execute(
                    """INSERT INTO obs.tenants(tenant_id,display_name,status,has_mysql,has_mongo)
                    VALUES(%s,%s,%s,%s,false)""",
                    (
                        tenant,
                        tenant,
                        "paused" if name == "paused" else "active",
                        name != "no_sources",
                    ),
                )
                if name in {"no_sources", "never_succeeded"}:
                    continue
                conn.execute(
                    """INSERT INTO obs.pipeline_runs(run_key,tenant_id,source_type,load_type,status,
                    started_at,ended_at,duration_s)
                    VALUES(%s,%s,'mysql','cdc','success',now()-(%s+1)*interval '1 minute',
                    now()-%s*interval '1 minute',60)""",
                    (
                        tenant + ":success",
                        tenant,
                        100 if name == "warning" else 10,
                        100 if name == "warning" else 10,
                    ),
                )
                if name in {
                    "recent_failure",
                    "failed_cdc",
                    "queued_after_failed",
                    "paused",
                }:
                    conn.execute(
                        """INSERT INTO obs.pipeline_runs(run_key,tenant_id,source_type,load_type,status,
                        started_at,ended_at,duration_s)
                        VALUES(%s,%s,'mysql',%s,'failed',now()-interval '5 minutes',
                        now()-interval '4 minutes',60)""",
                        (
                            tenant + ":failed",
                            tenant,
                            "initial" if name == "recent_failure" else "cdc",
                        ),
                    )
                if name == "queued_after_failed":
                    conn.execute(
                        """INSERT INTO obs.pipeline_runs(run_key,tenant_id,source_type,load_type,status,queued_at)
                        VALUES(%s,%s,'mysql','cdc','queued',now())""",
                        (tenant + ":queued", tenant),
                    )
                if name == "stuck":
                    conn.execute(
                        """INSERT INTO obs.pipeline_runs(run_key,tenant_id,source_type,load_type,status,started_at)
                        VALUES(%s,%s,'mysql','cdc','running',now()-interval '6 minutes')""",
                        (tenant + ":running", tenant),
                    )
            fixture_ids = [f"{prefix}_{name}" for name in cases]
            actual = conn.execute(
                "SELECT * FROM obs.v_tenant_health WHERE tenant_id=ANY(%s) ORDER BY tenant_id",
                (fixture_ids,),
            ).fetchall()
            reference = conn.execute(
                "SELECT * FROM ("
                + original
                + ") original WHERE tenant_id=ANY(%s) ORDER BY tenant_id",
                (fixture_ids,),
            ).fetchall()
            assert actual == reference
            health = {row["tenant_id"]: row["health"] for row in actual}
            for name, expected in cases.items():
                assert health[f"{prefix}_{name}"] == expected, name
        finally:
            # All edge-case fixtures are private to this transaction. Parallel
            # browser walks never see extra demo tenants or transient failures.
            conn.rollback()
