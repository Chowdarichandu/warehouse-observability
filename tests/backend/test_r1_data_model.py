from datetime import UTC, datetime, timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

from obs.db import connection, one, rows
from obs.repositories import analytics


def test_v3_schema_entities_and_module_registry() -> None:
    tables = {
        item["table_name"]
        for item in rows(
            """SELECT table_name FROM information_schema.tables
            WHERE table_schema='obs' AND table_type='BASE TABLE'"""
        )
    }
    assert {
        "tenants",
        "pipeline_runs",
        "run_stream_stats",
        "error_groups",
        "run_errors",
        "run_logs",
        "warehouse_snapshots",
        "schema_snapshots",
        "platform_health",
        "collector_state",
        "incidents",
        "alerts",
        "incident_notes",
        "alert_rules",
        "notification_channels",
        "notification_outbox",
        "maintenance_windows",
        "silences",
        "operations",
        "tenant_events",
        "quality_checks",
        "quality_results",
        "dependency_edges",
        "runbooks",
        "saved_views",
        "users",
        "roles",
        "sessions",
        "password_reset_tokens",
        "invites",
        "api_tokens",
        "audit_log",
        "app_settings",
        "daily_rollups",
        "warehouse_daily_rollups",
        "platform_daily_rollups",
        "modules",
        "role_modules",
        "user_module_overrides",
    } <= tables

    views = {
        item["table_name"]
        for item in rows(
            """SELECT table_name FROM information_schema.views
            WHERE table_schema='obs'"""
        )
    }
    assert {
        "v_latest_runs",
        "v_freshness",
        "v_stuck_runs",
        "v_tenant_health",
        "v_metric_runs",
        "v_mttr",
    } <= views

    modules = {
        item["module_id"]: item
        for item in rows("SELECT module_id,enabled FROM obs.modules")
    }
    assert modules["pravah"]["enabled"] is True
    assert all(not modules[name]["enabled"] for name in ("hrms", "finance", "sap"))


def test_metric_functions_follow_the_shared_contract() -> None:
    values = one(
        """SELECT obs.metric_success_rate(95,5) AS success_rate,
            obs.metric_success_rate(0,0) AS empty_success_rate,
            obs.metric_data_age_minutes(
                '2026-01-01T02:00:00Z','2026-01-01T00:30:00Z'
            ) AS data_age_min,
            obs.metric_is_fresh(
                '2026-01-01T02:00:00Z','2026-01-01T00:00:01Z',120
            ) AS fresh,
            obs.metric_is_fresh(
                '2026-01-01T02:00:00Z','2026-01-01T00:00:00Z',120
            ) AS at_boundary,
            obs.metric_is_fresh(
                '2026-01-01T02:00:00Z','2025-12-31T23:59:59Z',120
            ) AS late,
            obs.metric_stuck_threshold(100,51) AS stuck_threshold"""
    )
    assert float(values["success_rate"]) == 95.0
    assert values["empty_success_rate"] is None
    assert float(values["data_age_min"]) == 90.0
    assert values["fresh"] is True
    assert values["at_boundary"] is True
    assert values["late"] is False
    assert float(values["stuck_threshold"]) == 304.0


def test_sla_uses_cdc_age_and_excludes_maintenance_buckets() -> None:
    tenant = "r1_sla_" + uuid4().hex[:10]
    run_key = tenant + "|cdc"
    start = (datetime.now(UTC) - timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )
    end = start + timedelta(minutes=30)
    with connection() as conn:
        conn.execute(
            """INSERT INTO obs.tenants(
                tenant_id,display_name,status,has_mysql,has_mongo,sources,
                warehouse_schema,freshness_sla_min,registered_at
            ) VALUES(%s,'R1 metric fixture','active',true,false,%s,%s,15,%s)""",
            (tenant, Jsonb({"mysql": {"database_per_tenant": True}}), tenant, start),
        )
        conn.execute(
            """INSERT INTO obs.pipeline_runs(
                run_key,tenant_id,source_type,load_type,status,started_at,ended_at,duration_s
            ) VALUES(%s,%s,'mysql','cdc','success',%s,%s,60)""",
            (run_key, tenant, start - timedelta(minutes=1), start),
        )
        conn.execute(
            """INSERT INTO obs.maintenance_windows(
                tenant_id,starts_at,ends_at,reason,created_by
            ) VALUES(%s,%s,%s,'R1 metric fixture','test')""",
            (tenant, start + timedelta(minutes=10), start + timedelta(minutes=20)),
        )

    try:
        item = next(
            metric
            for metric in analytics.sla(start=start, end=end)
            if metric["tenant_id"] == tenant
        )
        assert item["buckets"] == 4
        assert item["good_buckets"] == 2
        assert float(item["compliance"]) == 50.0
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.pipeline_runs WHERE run_key=%s", (run_key,))
            conn.execute("DELETE FROM obs.tenants WHERE tenant_id=%s", (tenant,))


def test_volume_anomalies_filter_small_growth_and_rank_drops_first() -> None:
    tenant = "r1_volume_" + uuid4().hex[:10]
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(
        hours=4
    )
    snapshots = [
        (
            tenant,
            "fixture_table",
            100_000 + index * 100,
            start + timedelta(minutes=15 * index),
        )
        for index in range(9)
    ]
    snapshots.extend(
        [
            (tenant, "fixture_table", 107_000, start + timedelta(minutes=135)),
            (tenant, "fixture_table", 64_200, start + timedelta(minutes=150)),
        ]
    )
    with connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO obs.warehouse_snapshots(tenant_id,table_name,row_count,checked_at)
                VALUES(%s,%s,%s,%s)""",
                snapshots,
            )

    try:
        anomalies = [
            item for item in analytics.anomalies() if item["tenant_id"] == tenant
        ]
        assert [float(item["change_pct"]) for item in anomalies] == [-40.0, 6.2]
    finally:
        with connection() as conn:
            conn.execute(
                "DELETE FROM obs.warehouse_snapshots WHERE tenant_id=%s", (tenant,)
            )


def test_retention_rolls_up_before_pruning_raw_rows() -> None:
    from obs.maintenance import retain

    tenant = "r1_retention_" + uuid4().hex[:10]
    run_key = tenant + "|old-run"
    old_run = datetime.now(UTC) - timedelta(days=420)
    old_snapshot = datetime.now(UTC) - timedelta(days=40)
    old_audit = datetime.now(UTC) - timedelta(days=800)
    with connection() as conn:
        conn.execute(
            "INSERT INTO obs.tenants(tenant_id,display_name,status) VALUES(%s,'R1 retention fixture','offboarded')",
            (tenant,),
        )
        conn.execute(
            """INSERT INTO obs.pipeline_runs(
                run_key,tenant_id,source_type,load_type,status,started_at,ended_at,duration_s
            ) VALUES(%s,%s,'mysql','cdc','success',%s,%s,120)""",
            (run_key, tenant, old_run, old_run + timedelta(minutes=2)),
        )
        conn.execute(
            "INSERT INTO obs.run_logs(run_key,source,content) VALUES(%s,'airflow','old log')",
            (run_key,),
        )
        conn.execute(
            """INSERT INTO obs.warehouse_snapshots(tenant_id,table_name,row_count,checked_at)
            VALUES(%s,'old_table',123,%s)""",
            (tenant, old_snapshot),
        )
        conn.execute(
            """INSERT INTO obs.platform_health(component,status,checked_at)
            VALUES(%s,'up',%s)""",
            (tenant + "_component", old_snapshot),
        )
        conn.execute(
            """INSERT INTO obs.audit_log(actor,action,target,at)
            VALUES('test','retention_fixture',%s,%s)""",
            (tenant, old_audit),
        )

    try:
        retain()
        run_day = old_run.date()
        snapshot_day = old_snapshot.date()
        assert one("SELECT 1 FROM obs.pipeline_runs WHERE run_key=%s", (run_key,)) == {}
        assert one("SELECT 1 FROM obs.run_logs WHERE run_key=%s", (run_key,)) == {}
        assert one(
            """SELECT successes,run_count FROM obs.daily_rollups
            WHERE day=%s AND tenant_id=%s AND source_type='mysql' AND load_type='cdc'""",
            (run_day, tenant),
        ) == {"successes": 1, "run_count": 1}
        assert (
            one(
                "SELECT 1 FROM obs.warehouse_snapshots WHERE tenant_id=%s AND table_name='old_table'",
                (tenant,),
            )
            == {}
        )
        assert one(
            """SELECT samples,max_row_count FROM obs.warehouse_daily_rollups
            WHERE day=%s AND tenant_id=%s AND table_name='old_table'""",
            (snapshot_day, tenant),
        ) == {"samples": 1, "max_row_count": 123}
        assert one(
            """SELECT up_count,last_status FROM obs.platform_daily_rollups
            WHERE day=%s AND component=%s""",
            (snapshot_day, tenant + "_component"),
        ) == {"up_count": 1, "last_status": "up"}
        assert (
            one(
                "SELECT 1 FROM obs.audit_log WHERE target=%s AND action='retention_fixture'",
                (tenant,),
            )
            == {}
        )
    finally:
        with connection() as conn:
            conn.execute("DELETE FROM obs.daily_rollups WHERE tenant_id=%s", (tenant,))
            conn.execute(
                "DELETE FROM obs.warehouse_daily_rollups WHERE tenant_id=%s", (tenant,)
            )
            conn.execute(
                "DELETE FROM obs.platform_daily_rollups WHERE component=%s",
                (tenant + "_component",),
            )
            conn.execute("DELETE FROM obs.tenants WHERE tenant_id=%s", (tenant,))
