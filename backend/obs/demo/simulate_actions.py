from datetime import UTC, datetime, timedelta

from obs.db import connection, notify
from obs.demo.scenarios import MESSAGES, enrich_failure, upsert_run
from obs.demo.seed import make_run
from obs.onboarding.workflow import demo_tick
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
                        done = demo_tick(conn, job, now)
                        conn.execute(
                            "UPDATE obs.demo_jobs SET step=step+1,done=%s,due_at=%s WHERE job_key=%s",
                            (
                                done,
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
                if job["kind"] == "onboarding":
                    from obs.onboarding.workflow import latest, update_node

                    workflow = conn.execute(
                        "SELECT workflow_id FROM obs.onboarding_workflows WHERE tenant_id=%s",
                        (job["tenant_id"],),
                    ).fetchone()
                    if workflow:
                        workflow_id = str(workflow["workflow_id"])
                        for node in latest(conn, workflow_id):
                            if node["status"] in {"queued", "running"}:
                                update_node(
                                    conn, workflow_id, node["node_id"], "failed", error=str(exc)
                                )
                        conn.execute(
                            "UPDATE obs.onboarding_workflows SET state='failed',updated_at=now() WHERE workflow_id=%s",
                            (workflow_id,),
                        )
                    conn.execute(
                        "UPDATE obs.demo_jobs SET done=true WHERE job_key=%s", (job["job_key"],)
                    )
                else:
                    conn.execute(
                        "UPDATE obs.demo_jobs SET due_at=now()+interval '10 seconds' WHERE job_key=%s",
                        (job["job_key"],),
                    )
