import logging
import re
import signal
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from obs.collector.normalize import failure, normalize, tenant_for
from obs.collector.store import save
from obs.db import connection, one, rows
from obs.integrations import warehouse
from obs.integrations.airbyte import Airbyte, timestamp
from obs.integrations.airflow import Airflow
from obs.redact import redact
from obs.settings import require_live, settings


def checkpoint(component: str, work: Callable[[datetime], None]) -> None:
    started = time.monotonic()
    now = datetime.now(UTC)
    last = one("SELECT watermark FROM obs.collector_state WHERE component=%s", (component,))
    since = (last.get("watermark") or now - timedelta(days=7)) - timedelta(minutes=10)
    error = None
    try:
        work(since)
    except Exception as exc:
        error = redact(str(exc))[:2048]
        logging.error("%s: %s", component, error)
    with connection() as conn:
        conn.execute(
            """INSERT INTO obs.collector_state(component,watermark,last_success_at,last_poll_ms,last_error)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(component) DO UPDATE SET
            watermark=coalesce(excluded.watermark,obs.collector_state.watermark),
            last_success_at=coalesce(excluded.last_success_at,obs.collector_state.last_success_at),
            last_poll_ms=excluded.last_poll_ms,last_error=excluded.last_error,updated_at=now()""",
            (
                component,
                now if error is None else None,
                now if error is None else None,
                int((time.monotonic() - started) * 1000),
                error,
            ),
        )


def poll() -> None:
    require_live()
    af, ab = Airflow(), Airbyte()
    tenants = rows("SELECT * FROM obs.tenants WHERE status<>'offboarded'")
    with connection() as conn:
        conn.execute("""INSERT INTO obs.tenants(tenant_id,display_name,status,has_mysql,has_mongo)
            VALUES('_unmapped','Unmapped runs','paused',true,true) ON CONFLICT DO NOTHING""")
    for pipeline, dag in settings().airflow_dags.items():
        source, load = pipeline.split("_", 1)

        def collect_dag(
            since: datetime,
            dag: str = dag,
            source: str = source,
            load: str = load,
            pipeline: str = pipeline,
        ) -> None:
            errors = []
            dag_runs = af.runs(dag, since)
            known = {r["dag_run_id"] for r in dag_runs}
            for pending in rows(
                "SELECT DISTINCT dag_run_id,scheduled_for AS logical_date FROM obs.pipeline_runs WHERE dag_id=%s AND status IN ('queued','running')",
                (dag,),
            ):
                if pending["dag_run_id"] not in known:
                    dag_runs.append(pending)
            for dag_run in dag_runs:
                for task in af.tasks(dag, dag_run["dag_run_id"]):
                    if not re.search(
                        settings().sync_task_regex, task["task_id"]
                    ) and "Airbyte" not in task.get("operator", ""):
                        continue
                    task.update(
                        dag_id=dag,
                        dag_run_id=dag_run["dag_run_id"],
                        logical_date=dag_run.get("logical_date"),
                    )
                    try:
                        job_id = af.job_id(task)
                        job = ab.job(job_id) if job_id is not None else {}
                        tenant = tenant_for(task, job, tenants, settings().tenant_task_regex)
                        if not job and tenant and task.get("start_date"):
                            connection_id = tenant["airbyte_connections"].get(pipeline)
                            if connection_id:
                                candidates = ab.jobs(
                                    connection_id,
                                    timestamp(task["start_date"]) - timedelta(minutes=5),
                                )
                                matches = [
                                    j
                                    for j in candidates
                                    if timestamp(j.get("startTime") or j.get("createdAt"))
                                    and abs(
                                        (
                                            timestamp(j.get("startTime") or j.get("createdAt"))
                                            - timestamp(task["start_date"])
                                        ).total_seconds()
                                    )
                                    <= 300
                                ]
                                if len(matches) == 1:
                                    job = ab.job(matches[0]["jobId"])
                        run = normalize(
                            task, job, tenant["tenant_id"] if tenant else "_unmapped", source, load
                        )
                        if not run["airbyte_connection_id"] and tenant:
                            run["airbyte_connection_id"] = tenant["airbyte_connections"].get(
                                pipeline
                            )
                        message, origin, job_log, streams = failure(job)
                        task_log = ""
                        if run["status"] == "failed":
                            try:
                                task_log = af.log(task)
                            except Exception as exc:
                                errors.append("Task log unavailable: " + redact(str(exc)))
                                task_log = "Task log could not be fetched. Check Airflow Viewer log permissions and API version."
                        if job.get("diagnostic_error"):
                            errors.append(job["diagnostic_error"])
                        with connection() as conn:
                            save(
                                conn,
                                run,
                                message=message or task_log[-2048:],
                                origin=origin,
                                log=task_log + "\n" + job_log,
                                streams=streams,
                            )
                    except Exception as exc:
                        errors.append(redact(str(exc)))
            if errors:
                raise RuntimeError(f"{len(errors)} task(s) failed to collect: {errors[0]}")

        checkpoint(f"airflow:{dag}", collect_dag)
    for tenant in tenants:
        for pipeline, connection_id in tenant["airbyte_connections"].items():

            def collect_jobs(
                since: datetime,
                tenant: dict = tenant,
                pipeline: str = pipeline,
                connection_id: str = connection_id,
            ) -> None:
                source, load = pipeline.split("_", 1)
                jobs = ab.jobs(connection_id, since)
                # Revisit pending/running Airbyte-only jobs even if the remote update filter omits them.
                pending = rows(
                    "SELECT airbyte_job_id FROM obs.pipeline_runs WHERE airbyte_connection_id=%s AND status IN ('queued','running') AND dag_id IS NULL",
                    (connection_id,),
                )
                ids = {j["jobId"] for j in jobs} | {
                    p["airbyte_job_id"] for p in pending if p["airbyte_job_id"]
                }
                errors = []
                for job_id in ids:
                    if one(
                        "SELECT 1 FROM obs.pipeline_runs WHERE airbyte_job_id=%s AND dag_id IS NOT NULL",
                        (job_id,),
                    ):
                        continue
                    try:
                        job = ab.job(job_id)
                        run = normalize(None, job, tenant["tenant_id"], source, load)
                        message, origin, log, streams = failure(job)
                        with connection() as conn:
                            save(
                                conn, run, message=message, origin=origin, log=log, streams=streams
                            )
                    except Exception as exc:
                        errors.append(redact(str(exc)))
                if errors:
                    raise RuntimeError(
                        f"{len(errors)} Airbyte job(s) failed to collect: {errors[0]}"
                    )

            checkpoint(f"airbyte:{connection_id}", collect_jobs)


def platform() -> None:
    def check(name: str, work: Callable[[], dict]) -> None:
        status, details = "up", {}
        try:
            details = work()
            if details.get("unhealthy"):
                status = "degraded"
        except Exception as exc:
            status, details = "down", {"error": redact(str(exc))}
        with connection() as conn:
            conn.execute(
                "INSERT INTO obs.platform_health(component,status,details) VALUES(%s,%s,%s)",
                (name, status, Jsonb(details)),
            )

    def airflow_health() -> dict:
        data = Airflow().health()
        return {
            "unhealthy": any(
                v.get("status") not in {"healthy", None}
                for v in data.values()
                if isinstance(v, dict)
            ),
            **data,
        }

    check("airflow_scheduler", airflow_health)

    def metadb_health() -> dict:
        data = Airflow().health().get("metadatabase", {})
        return {"unhealthy": data.get("status") != "healthy", **data}

    check("airflow_metadb", metadb_health)
    check("airflow_pools", lambda: {"pools": Airflow().pages("/pools", "pools")})

    def imports() -> dict:
        items = Airflow().pages("/importErrors", "import_errors")
        return {
            "unhealthy": bool(items),
            "errors": [
                {
                    "filename": i.get("filename"),
                    "stack_trace": redact(i.get("stack_trace", ""))[:2048],
                }
                for i in items
            ],
        }

    check("airflow_import_errors", imports)
    check(
        "airbyte",
        lambda: {
            "connections": len(
                Airbyte().call("GET", "/connections", params={"limit": 1}).get("data", [])
            )
        },
    )

    def warehouse_health() -> dict:
        with warehouse.connect() as conn:
            conn.execute("SELECT 1")
        return {"message": "Catalog connection available"}

    check("warehouse", warehouse_health)


def snapshots() -> None:
    for tenant in rows("SELECT * FROM obs.tenants WHERE status='active'"):

        def work(since: datetime, tenant: dict = tenant) -> None:
            with connection() as conn:
                warehouse.collect(conn, tenant)

        checkpoint(f"warehouse:{tenant['tenant_id']}", work)


def main() -> None:
    require_live()
    stopping = False

    def stop(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    from obs.maintenance import retain
    from obs.quality.engine import evaluate_due

    jobs = [
        (poll, settings().poll_interval_sec),
        (platform, settings().platform_check_sec),
        (snapshots, settings().warehouse_check_sec),
        (retain, 86400),
        (evaluate_due, settings().quality_interval_sec),
    ]
    due = {fn.__name__: 0.0 for fn, _ in jobs}
    while not stopping:
        try:
            with connection() as leader:
                leader.commit()
                leader.autocommit = True
                if leader.execute("SELECT pg_try_advisory_lock(110540) AS acquired").fetchone()[
                    "acquired"
                ]:
                    for fn, interval in jobs:
                        if time.monotonic() >= due[fn.__name__]:
                            checkpoint("worker:" + fn.__name__, lambda since, fn=fn: fn())
                            due[fn.__name__] = time.monotonic() + interval
        except Exception as exc:
            logging.error("Collector loop: %s", redact(str(exc)))
        time.sleep(1)
