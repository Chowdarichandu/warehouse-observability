from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from obs.db import connection, notify
from obs.demo.scenarios import MESSAGES, enrich_failure, upsert_run
from obs.demo.seed import make_run
from obs.onboarding.service import STEPS
from obs.settings import settings


def process_jobs() -> None:
    now = datetime.now(UTC)
    with connection() as conn:
        jobs = conn.execute(
            "SELECT * FROM obs.demo_jobs WHERE NOT done AND due_at<=now() FOR UPDATE SKIP LOCKED"
        ).fetchall()
        for job in jobs:
            try:
                with conn.transaction():
                    if job["kind"] == "retry":
                        run = conn.execute(
                            """UPDATE obs.pipeline_runs SET status='success',ended_at=%s,
                            duration_s=greatest(1,extract(epoch FROM %s-started_at)::integer),rows_synced=84000,bytes_synced=13440000
                            WHERE run_key=%s RETURNING *""",
                            (now, now, job["payload"]["run_key"]),
                        ).fetchone()
                        if run["tenant_id"] == "acme_retail" and run["source_type"] == "mysql":
                            # The task retry completed, but the next scheduled check still sees the missing binlog.
                            run = make_run(
                                "acme_retail",
                                "mysql",
                                "cdc",
                                now,
                                0,
                                int(now.timestamp() * 1000) + 1,
                                "failed",
                            )
                            upsert_run(conn, run)
                            enrich_failure(conn, run, MESSAGES["MYSQL_BINLOG_PURGED"])
                        notify(
                            conn,
                            "run.updated",
                            {
                                "run_key": job["payload"]["run_key"],
                                "tenant_id": job["tenant_id"],
                                "status": "success",
                            },
                        )
                        conn.execute(
                            "UPDATE obs.demo_jobs SET done=true WHERE job_key=%s", (job["job_key"],)
                        )
                    elif job["kind"] == "onboarding":
                        step = job["step"]
                        tenant = job["tenant_id"]
                        data = job["payload"]
                        if step == 2:
                            mapping = {
                                f"{s}_{load_kind}": f"demo-{tenant}-{s}-{load_kind}"
                                for s in ("mysql", "mongo")
                                if data[f"has_{s}"]
                                for load_kind in ("initial", "cdc")
                            }
                            conn.execute(
                                "UPDATE obs.tenants SET airbyte_connections=%s WHERE tenant_id=%s",
                                (Jsonb(mapping), tenant),
                            )
                        if step == 4 and data["run_initial"]:
                            for source in ("mysql", "mongo"):
                                if data[f"has_{source}"]:
                                    run = make_run(
                                        tenant,
                                        source,
                                        "initial",
                                        now,
                                        0,
                                        int(now.timestamp() * 1000) + (source == "mongo"),
                                        "running",
                                        "onboarding",
                                    )
                                    upsert_run(conn, run)
                        if step == 5:
                            conn.execute(
                                "UPDATE obs.tenants SET status='active',updated_at=now() WHERE tenant_id=%s",
                                (tenant,),
                            )
                            conn.execute(
                                """UPDATE obs.pipeline_runs SET status='success',ended_at=%s,
                                duration_s=greatest(1,extract(epoch FROM %s-started_at)::integer),rows_synced=120000,bytes_synced=19200000
                                WHERE tenant_id=%s AND status='running'""",
                                (now, now, tenant),
                            )
                            if not data["run_initial"]:
                                # Registering without initial loads leaves freshness unsatisfied until the first sync.
                                pass
                            else:
                                for table in (
                                    "customers",
                                    "orders",
                                    "products",
                                    "payments",
                                    "events",
                                ):
                                    conn.execute(
                                        "INSERT INTO obs.warehouse_snapshots VALUES(%s,%s,24000,%s,%s)",
                                        (tenant, table, now, now),
                                    )
                        conn.execute(
                            "INSERT INTO obs.tenant_events(tenant_id,step,status,message) VALUES(%s,%s,'ok',%s)",
                            (tenant, STEPS[step], "Completed in demo mode"),
                        )
                        notify(
                            conn,
                            "onboarding.step",
                            {"tenant_id": tenant, "step": STEPS[step], "status": "ok"},
                        )
                        if step < 5:
                            conn.execute(
                                "INSERT INTO obs.tenant_events(tenant_id,step,status,message) VALUES(%s,%s,'started','In progress')",
                                (tenant, STEPS[step + 1]),
                            )
                        conn.execute(
                            "UPDATE obs.demo_jobs SET step=step+1,done=%s,due_at=%s WHERE job_key=%s",
                            (
                                step >= 5,
                                now + timedelta(seconds=settings().demo_onboard_step_sec),
                                job["job_key"],
                            ),
                        )
            except Exception as exc:
                from obs.redact import redact

                conn.execute(
                    "INSERT INTO obs.tenant_events(tenant_id,step,status,message) VALUES(%s,'demo worker','failed',%s)",
                    (job["tenant_id"], redact(str(exc))),
                )
                conn.execute(
                    "UPDATE obs.demo_jobs SET due_at=now()+interval '10 seconds' WHERE job_key=%s",
                    (job["job_key"],),
                )
