import logging
import random
import time
from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from obs.db import connection, notify
from obs.demo.scenarios import MESSAGES, enrich_failure, upsert_run
from obs.demo.seed import STREAMS, TENANTS, make_run, seed
from obs.demo.simulate_actions import process_jobs
from obs.quality.engine import evaluate_due
from obs.redact import redact
from obs.settings import require_demo, settings


def tick() -> None:
    now = datetime.now(UTC)
    bucket = int(now.timestamp() // settings().demo_tick_sec)
    sizes = {t: s for t, _, s in TENANTS}
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110530)")
        conn.execute(
            """UPDATE obs.pipeline_runs SET status='success',ended_at=%s,
            duration_s=extract(epoch FROM %s-started_at)::integer,rows_synced=96000,bytes_synced=15360000
            WHERE status='running' AND triggered_by='schedule' AND tenant_id<>'northwind'
            AND started_at<%s-interval '1 minute'""",
            (now, now, now),
        )
        for tenant in conn.execute("SELECT * FROM obs.tenants WHERE status='active'").fetchall():
            try:
                with conn.transaction():
                    tid = tenant["tenant_id"]
                    # Keep the Bluefin near-SLA recovery and the Northwind stuck-run scenario visible.
                    if tid in {"bluefin_health", "northwind"}:
                        continue
                    rng = random.Random(f"{tid}-{bucket}")
                    source = rng.choice([s for s in ("mysql", "mongo") if tenant[f"has_{s}"]])
                    duration = max(60, int(sizes.get(tid, 4) * 60 * rng.lognormvariate(0, 0.25)))
                    at = now - timedelta(seconds=duration + 2)
                    is_outage = (
                        tid == "acme_retail"
                        and source == "mysql"
                        and not conn.execute(
                            "SELECT 1 FROM obs.demo_jobs WHERE job_key='resync:acme_retail'"
                        ).fetchone()
                    )
                    if is_outage:
                        at = now - timedelta(seconds=10)
                        duration = 8
                    run = make_run(
                        tid,
                        source,
                        "cdc",
                        at,
                        duration,
                        bucket * 100 + len(tid),
                        "failed" if is_outage else "success",
                    )
                    run["run_key"] = f"demo|{bucket}|{tid}|{source}"
                    run["collected_at"] = now
                    upsert_run(conn, run)
                    if is_outage:
                        enrich_failure(conn, run, MESSAGES["MYSQL_BINLOG_PURGED"])
                    else:
                        with conn.cursor() as cur:
                            cur.executemany(
                                """INSERT INTO obs.run_stream_stats(run_key,stream_name,records,bytes)
                                VALUES(%s,%s,%s,%s) ON CONFLICT(run_key,stream_name) DO UPDATE SET records=excluded.records,bytes=excluded.bytes""",
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
                    notify(
                        conn,
                        "run.updated",
                        {
                            k: run[k]
                            for k in ("run_key", "tenant_id", "status", "source_type", "load_type")
                        },
                    )
            except Exception as exc:
                conn.execute(
                    """INSERT INTO obs.collector_state(component,last_error) VALUES(%s,%s)
                    ON CONFLICT(component) DO UPDATE SET last_error=excluded.last_error,updated_at=now()""",
                    (f"tenant:{tenant['tenant_id']}", redact(str(exc))),
                )
        components = [
            "airflow_scheduler",
            "airflow_metadb",
            "airflow_pools",
            "airflow_import_errors",
            "airbyte",
            "warehouse",
            "collector",
        ]
        for component in components:
            details = {"message": "Demo check passed"}
            if component == "airflow_pools":
                details = {"pool": "default_pool", "occupied": 12, "queued": 2, "slots": 32}
            conn.execute(
                "INSERT INTO obs.platform_health(component,status,details,checked_at) VALUES(%s,'up',%s,%s) ON CONFLICT DO NOTHING",
                (component, Jsonb(details), now),
            )
        for component in ("airflow", "airbyte", "warehouse", "demo_ticker"):
            conn.execute(
                """INSERT INTO obs.collector_state(component,watermark,last_success_at,last_poll_ms)
                VALUES(%s,%s,%s,86) ON CONFLICT(component) DO UPDATE SET watermark=excluded.watermark,
                last_success_at=excluded.last_success_at,last_poll_ms=excluded.last_poll_ms,last_error=NULL,updated_at=now()""",
                (component, now, now),
            )
        notify(conn, "platform.changed", {"status": "up", "checked_at": now.isoformat()})


def warehouse_tick() -> None:
    """Advance catalog snapshots every 15 seconds (15 simulated minutes)."""
    now = datetime.now(UTC)
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110532)")
        tables = conn.execute("""SELECT DISTINCT ON(w.tenant_id,w.table_name) w.* FROM obs.warehouse_snapshots w
            JOIN obs.tenants t USING(tenant_id) WHERE t.status='active' ORDER BY w.tenant_id,w.table_name,w.checked_at DESC""").fetchall()
        for table in tables:
            try:
                with conn.transaction():
                    loaded = conn.execute(
                        "SELECT max(ended_at) AS at FROM obs.pipeline_runs WHERE tenant_id=%s AND status='success'",
                        (table["tenant_id"],),
                    ).fetchone()["at"]
                    conn.execute(
                        "INSERT INTO obs.warehouse_snapshots VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (
                            table["tenant_id"],
                            table["table_name"],
                            table["row_count"] + 17,
                            loaded,
                            now,
                        ),
                    )
                    schema = conn.execute(
                        "SELECT * FROM obs.schema_snapshots WHERE tenant_id=%s AND table_name=%s ORDER BY checked_at DESC LIMIT 1",
                        (table["tenant_id"], table["table_name"]),
                    ).fetchone()
                    if schema:
                        conn.execute(
                            "INSERT INTO obs.schema_snapshots VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (
                                table["tenant_id"],
                                table["table_name"],
                                Jsonb(schema["columns"]),
                                schema["columns_hash"],
                                now,
                            ),
                        )
            except Exception as exc:
                conn.execute(
                    """INSERT INTO obs.collector_state(component,last_error) VALUES(%s,%s)
                    ON CONFLICT(component) DO UPDATE SET last_error=excluded.last_error,updated_at=now()""",
                    (f"warehouse:{table['tenant_id']}", redact(str(exc))),
                )


def main() -> None:
    require_demo()
    seed()
    last_tick = time.monotonic()
    last_warehouse = time.monotonic()
    while True:
        try:
            process_jobs()
            if time.monotonic() - last_warehouse >= max(1, settings().demo_tick_sec / 4):
                warehouse_tick()
                evaluate_due()
                last_warehouse = time.monotonic()
            if time.monotonic() - last_tick >= settings().demo_tick_sec:
                tick()
                last_tick = time.monotonic()
        except Exception as exc:
            logging.error("Demo ticker: %s", redact(str(exc)))
        time.sleep(1)


if __name__ == "__main__":
    main()
