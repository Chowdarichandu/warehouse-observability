import hashlib
import json
import random
from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from obs.auth import hasher
from obs.db import connection, notify
from obs.demo.scenarios import MESSAGES, enrich_failure, upsert_run
from obs.settings import require_demo, settings

TENANTS = [
    ("acme_retail", "Acme Retail", 4),
    ("bluefin_health", "Bluefin Health", 3),
    ("northwind", "Northwind", 17),
    ("orbit_logistics", "Orbit Logistics", 11),
    ("cedar_foods", "Cedar Foods", 5),
    ("helix_energy", "Helix Energy", 14),
    ("evergreen_market", "Evergreen Market", 2),
    ("summit_media", "Summit Media", 4),
    ("luminous_labs", "Luminous Labs", 3),
    ("beacon_finance", "Beacon Finance", 9),
]
STREAMS = [
    "customers",
    "orders",
    "products",
    "payments",
    "events",
    "inventory",
    "invoices",
    "sessions",
]
DEFAULT_RULES = [
    ("cdc_consecutive_failures", "Consecutive CDC failures", "high", {"n": 2}),
    ("cdc_position_lost", "CDC replication position lost", "critical", {}),
    ("freshness_breach", "Freshness SLA breached", "high", {"pct": 100}),
    ("stuck_run", "Run exceeds usual duration", "medium", {"multiplier": 3}),
    ("volume_anomaly", "Warehouse volume anomaly", "medium", {"drop_pct": 30}),
    ("schema_drift", "Warehouse schema changed", "low", {}),
    ("queue_backlog", "Airflow queue backlog", "medium", {"minutes": 15}),
    ("dag_import_errors", "DAG import errors", "high", {}),
    ("platform_down", "Platform component down", "critical", {}),
    ("collector_silent", "Collector heartbeat missing", "critical", {"minutes": 10}),
]


def make_run(
    tenant: str,
    source: str,
    load: str,
    at: datetime,
    duration: int,
    job_id: int,
    status: str = "success",
    triggered_by: str = "schedule",
) -> dict:
    dag = f"{source}_{'initial_load' if load == 'initial' else 'cdc'}"
    return {
        "run_key": f"{dag}|scheduled__{at.isoformat()}|sync_{tenant}|-1",
        "tenant_id": tenant,
        "source_type": source,
        "load_type": load,
        "status": status,
        "failed_stage": "airbyte" if status == "failed" else None,
        "triggered_by": triggered_by,
        "scheduled_for": at - timedelta(seconds=20),
        "queued_at": at - timedelta(seconds=20),
        "started_at": at,
        "ended_at": at + timedelta(seconds=duration)
        if status not in {"running", "queued"}
        else None,
        "duration_s": duration if status not in {"running", "queued"} else None,
        "queue_delay_s": 20,
        "rows_synced": duration * 420 if status == "success" else 0,
        "bytes_synced": duration * 420 * 160 if status == "success" else 0,
        "dag_id": dag,
        "dag_run_id": f"scheduled__{at.isoformat()}",
        "task_id": f"sync_{tenant}",
        "map_index": -1,
        "try_number": 1,
        "airbyte_connection_id": f"demo-{tenant}-{source}-{load}",
        "airbyte_job_id": job_id,
        "airbyte_attempts": 1,
        "collected_at": at,
    }


def seed() -> None:
    require_demo()
    rng = random.Random(271828)
    now = datetime.now(UTC).replace(microsecond=0)
    anchor = now.replace(minute=0, second=0)
    outage = now.replace(hour=2, minute=0, second=0)
    if now - outage < timedelta(hours=3):
        outage -= timedelta(days=1)
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110528)")
        for role in ("admin", "operator", "viewer"):
            conn.execute(
                """INSERT INTO obs.users(email,display_name,role,password_hash) VALUES(%s,%s,%s,%s)
                ON CONFLICT(email) DO NOTHING""",
                (
                    f"{role}@demo.local",
                    f"Demo {role.title()}",
                    role,
                    hasher.hash(settings().demo_password),
                ),
            )
        for key, name, severity, params in DEFAULT_RULES:
            conn.execute(
                """INSERT INTO obs.alert_rules(rule_id,name,severity,params,channels) VALUES(%s,%s,%s,%s,%s)
                ON CONFLICT(rule_id) DO NOTHING""",
                (key, name, severity, Jsonb(params), ["slack-data-eng"]),
            )
        for channel, kind, env in [
            ("slack-data-eng", "slack", "SLACK_WEBHOOK_URL"),
            ("teams-operations", "teams", "TEAMS_WEBHOOK_URL"),
            ("email-oncall", "email", "SMTP_URL"),
        ]:
            conn.execute(
                "INSERT INTO obs.notification_channels(channel_id,kind,target_env) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (channel, kind, env),
            )
        if conn.execute("SELECT count(*) AS n FROM obs.pipeline_runs").fetchone()["n"]:
            from obs.quality.demo import seed_quality

            seed_quality(conn)
            print(
                "Demo history already present; seed is idempotent. Use make reset for a fresh history."
            )
            return
        for tenant, name, size in TENANTS:
            mapping = {
                f"{s}_{load_kind}": f"demo-{tenant}-{s}-{load_kind}"
                for s in ("mysql", "mongo")
                for load_kind in ("initial", "cdc")
            }
            conn.execute(
                """INSERT INTO obs.tenants(tenant_id,display_name,status,airbyte_connections,warehouse_schema,owner_email,created_at)
                VALUES(%s,%s,'active',%s,%s,%s,%s) ON CONFLICT(tenant_id) DO NOTHING""",
                (
                    tenant,
                    name,
                    Jsonb(mapping),
                    tenant,
                    f"data@{tenant}.example",
                    now - timedelta(days=45),
                ),
            )
            for hour in range(168, 0, -1):
                at = anchor - timedelta(hours=hour) + timedelta(seconds=rng.randint(0, 60))
                for source in ("mysql", "mongo"):
                    for load in ("initial", "cdc"):
                        duration = max(
                            45,
                            int(
                                rng.lognormvariate(0, 0.35)
                                * size
                                * 60
                                * (4 if load == "initial" else 1)
                            ),
                        )
                        duration = min(duration, int((now - at).total_seconds()) - 180)
                        fail = rng.random() < 0.033 and at < now - timedelta(hours=24)
                        error = rng.choice(list(MESSAGES))
                        if tenant == "cedar_foods" and at.hour < 5 and rng.random() < 0.48:
                            fail, error = True, "SOURCE_UNREACHABLE"
                        if tenant == "acme_retail" and source == "mysql" and at >= outage:
                            fail, error = True, "MYSQL_BINLOG_PURGED"
                        if (
                            tenant == "bluefin_health"
                            and source == "mongo"
                            and at > now - timedelta(minutes=125)
                        ):
                            # A recovery 100 min ago keeps this tenant degraded, as defined in §7.
                            continue
                        job_id = int(
                            hashlib.sha1(f"{tenant}{source}{load}{hour}".encode()).hexdigest()[:10],
                            16,
                        )
                        run = make_run(
                            tenant,
                            source,
                            load,
                            at,
                            duration,
                            job_id,
                            "failed" if fail else "success",
                        )
                        delay = rng.randint(4, 48) + (
                            rng.randint(90, 240) if 18 <= at.hour <= 21 else 0
                        )
                        run.update(
                            queue_delay_s=delay,
                            queued_at=at - timedelta(seconds=delay),
                            airbyte_attempts=3 if fail else 1,
                        )
                        if fail and error == "AIRFLOW_INFRA":
                            run["failed_stage"] = "airflow"
                        upsert_run(conn, run)
                        if fail:
                            enrich_failure(
                                conn,
                                run,
                                MESSAGES[error],
                                "destination" if error == "DESTINATION_ERROR" else "source",
                            )
                        else:
                            with conn.cursor() as cur:
                                cur.executemany(
                                    "INSERT INTO obs.run_stream_stats(run_key,stream_name,records,bytes) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                    [
                                        (
                                            run["run_key"],
                                            stream,
                                            run["rows_synced"] // len(STREAMS),
                                            run["bytes_synced"] // len(STREAMS),
                                        )
                                        for stream in STREAMS
                                    ],
                                )
            for table_index, table in enumerate(STREAMS):
                base = (table_index + 1) * size * 24000
                columns = [
                    {"name": "id", "type": "bigint"},
                    {"name": "created_at", "type": "timestamp"},
                    {"name": "amount", "type": "numeric"},
                ]
                for i in range(672, -1, -1):
                    checked = now - timedelta(minutes=i * 15)
                    count = base + max(0, 672 - i) * size * 19
                    if (
                        tenant == "orbit_logistics"
                        and table == "orders"
                        and checked >= now - timedelta(days=1)
                    ):
                        count = int(count * 0.6)
                    loaded = now - timedelta(
                        minutes=205
                        if tenant == "acme_retail"
                        else 100
                        if tenant == "bluefin_health"
                        else 12 + table_index
                    )
                    conn.execute(
                        "INSERT INTO obs.warehouse_snapshots VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (tenant, table, count, min(loaded, checked), checked),
                    )
                    snapshot = columns + (
                        [{"name": "delivery_region", "type": "text"}]
                        if tenant == "orbit_logistics"
                        and table == "orders"
                        and checked >= now - timedelta(days=1)
                        else []
                    )
                    digest = hashlib.sha256(
                        json.dumps(snapshot, sort_keys=True).encode()
                    ).hexdigest()
                    conn.execute(
                        "INSERT INTO obs.schema_snapshots VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (tenant, table, Jsonb(snapshot), digest, checked),
                    )
        for load in ("initial", "cdc"):
            run = make_run(
                "bluefin_health",
                "mongo",
                load,
                now - timedelta(minutes=112),
                180,
                88001 + (load == "cdc"),
                "failed",
            )
            run["airbyte_attempts"] = 3
            upsert_run(conn, run)
            enrich_failure(conn, run, MESSAGES["SOURCE_UNREACHABLE"])
            recovery = make_run(
                "bluefin_health",
                "mongo",
                load,
                now - timedelta(minutes=104),
                240,
                88011 + (load == "cdc"),
            )
            upsert_run(conn, recovery)
        stuck = make_run(
            "northwind", "mysql", "cdc", now - timedelta(minutes=58), 0, 99001, "running"
        )
        upsert_run(conn, stuck)
        for tenant, _, _ in TENANTS[3:]:
            if tenant == "cedar_foods":
                continue
            # Selected latest runs are visibly in progress without compromising source freshness.
            if tenant in {"orbit_logistics", "helix_energy", "summit_media"}:
                upsert_run(
                    conn,
                    make_run(
                        tenant,
                        "mongo",
                        "cdc",
                        now - timedelta(minutes=2),
                        0,
                        99002 + len(tenant),
                        "running",
                    ),
                )
        components = [
            "airflow_scheduler",
            "airflow_metadb",
            "airflow_pools",
            "airflow_import_errors",
            "airbyte",
            "warehouse",
            "collector",
            "alerter",
        ]
        for i in range(48 * 60, -1, -1):
            checked = now - timedelta(minutes=i)
            for comp in components:
                was_broken = comp == "airflow_import_errors" and now - timedelta(
                    hours=30
                ) <= checked < now - timedelta(hours=27)
                details = {
                    "message": "onboard_tenant.py: ModuleNotFoundError (fixed yesterday)"
                    if was_broken
                    else "All checks passing"
                }
                if comp == "airflow_pools":
                    details = {"pool": "default_pool", "occupied": 12, "queued": 2, "slots": 32}
                conn.execute(
                    "INSERT INTO obs.platform_health VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (comp, "degraded" if was_broken else "up", Jsonb(details), checked),
                )
        for comp in ("airflow", "airbyte", "warehouse", "demo_ticker"):
            conn.execute(
                "INSERT INTO obs.collector_state(component,watermark,last_success_at,last_poll_ms) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (comp, now, now, rng.randint(40, 185)),
            )
        notify(
            conn,
            "run.updated",
            {
                "tenant_id": "acme_retail",
                "status": "failed",
                "source_type": "mysql",
                "load_type": "cdc",
            },
        )
        from obs.quality.demo import seed_quality

        seed_quality(conn)
    from obs.alerter.rules import evaluate

    evaluate()
    print("Seeded 10 tenants, ~6,700 runs, 7 days of warehouse history and scripted scenarios.")


if __name__ == "__main__":
    seed()
