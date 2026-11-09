from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from psycopg.types.json import Jsonb

from obs.actions.retry import retry as retry_action
from obs.alerter.notify import deliver
from obs.alerter.rules import PARAMS
from obs.api import schemas as s
from obs.audit import audit
from obs.auth import fail, require_role
from obs.db import connection, notify, one
from obs.demo.scenarios import upsert_run
from obs.demo.seed import make_run
from obs.onboarding.preflight import preflight as run_preflight
from obs.onboarding.service import start
from obs.redact import redact
from obs.settings import require_demo

router = APIRouter(tags=["Audited actions"])


@router.post("/runs/{run_key}/retry", response_model=s.RetryResult)
def retry(run_key: str, user: dict = Depends(require_role("operator"))) -> dict:
    return retry_action(run_key, user["email"])


@router.patch("/tenants/{id}", response_model=s.Message)
def update_tenant(
    id: str, data: s.TenantPatch, user: dict = Depends(require_role("admin"))
) -> dict:
    require_demo()
    changes = data.model_dump(exclude_none=True)
    if not changes:
        fail(422, "empty_patch", "Supply at least one change.")
    with connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM obs.tenants WHERE tenant_id=%s FOR UPDATE", (id,)
        ).fetchone():
            fail(404, "tenant_not_found", "Tenant not found.")
        for key, value in changes.items():
            conn.execute(
                f"UPDATE obs.tenants SET {key}=%s,updated_at=now() WHERE tenant_id=%s", (value, id)
            )
        action = (
            "pause_tenant"
            if data.status == "paused"
            else "resume_tenant"
            if data.status == "active"
            else "update_tenant"
        )
        audit(conn, user["email"], action, id, changes)
        notify(conn, "run.updated", {"tenant_id": id, "status": data.status or "updated"})
    return {"message": "Tenant settings updated (demo)."}


@router.post("/tenants/{id}/resync", response_model=s.Message)
def resync(id: str, user: dict = Depends(require_role("admin"))) -> dict:
    require_demo()
    now = datetime.now(UTC)
    with connection() as conn:
        tenant = conn.execute(
            "SELECT * FROM obs.tenants WHERE tenant_id=%s FOR UPDATE", (id,)
        ).fetchone()
        if not tenant:
            fail(404, "tenant_not_found", "Tenant not found.")
        for source in ("mysql", "mongo"):
            if tenant[f"has_{source}"]:
                for load in ("initial", "cdc"):
                    run = make_run(
                        id,
                        source,
                        load,
                        now,
                        0,
                        int(now.timestamp() * 1000) + (source == "mongo"),
                        "success",
                        "manual",
                    )
                    upsert_run(conn, run)
        conn.execute(
            "INSERT INTO obs.demo_jobs(job_key,kind,tenant_id,payload,done) VALUES(%s,'resync',%s,'{}',true) ON CONFLICT DO NOTHING",
            (f"resync:{id}", id),
        )
        audit(conn, user["email"], "demo_resync", id, {"simulated": True})
        notify(conn, "run.updated", {"tenant_id": id, "status": "success", "action": "resync"})
    return {
        "message": "Simulated resync restored the replication position. Historical failures remain visible."
    }


@router.post("/alerts/{id}/ack", response_model=s.Message)
def ack(id: int, user: dict = Depends(require_role("operator"))) -> dict:
    with connection() as conn:
        alert = conn.execute("SELECT * FROM obs.alerts WHERE id=%s FOR UPDATE", (id,)).fetchone()
        if not alert:
            fail(404, "alert_not_found", "Alert not found.")
        if alert["state"] == "resolved":
            fail(409, "alert_resolved", "A resolved alert cannot be acknowledged.")
        conn.execute(
            "UPDATE obs.alerts SET state='acked',acked_by=%s,acked_at=now() WHERE id=%s",
            (user["email"], id),
        )
        audit(conn, user["email"], "ack_alert", str(id))
        notify(conn, "alert.fired", {"id": id, "state": "acked", "tenant_id": alert["tenant_id"]})
    return {"message": "Alert acknowledged. Repeat notifications are muted."}


@router.post("/alerts/{id}/resolve", response_model=s.Message)
def resolve(id: int, user: dict = Depends(require_role("operator"))) -> dict:
    with connection() as conn:
        alert = conn.execute("SELECT * FROM obs.alerts WHERE id=%s FOR UPDATE", (id,)).fetchone()
        if not alert:
            fail(404, "alert_not_found", "Alert not found.")
        conn.execute("UPDATE obs.alerts SET state='resolved',resolved_at=now() WHERE id=%s", (id,))
        audit(conn, user["email"], "resolve_alert", str(id))
        rule = conn.execute(
            "SELECT channels FROM obs.alert_rules WHERE rule_id=%s", (alert["rule_id"],)
        ).fetchone()
        for channel in rule["channels"]:
            deliver(conn, channel, "resolved", alert["title"], id)
        notify(conn, "alert.resolved", {"id": id, "tenant_id": alert["tenant_id"]})
    return {"message": "Alert resolved. It may fire again if the condition persists."}


@router.put("/alert-rules/{id}", response_model=s.Rule)
def update_rule(id: str, data: s.RulePatch, user: dict = Depends(require_role("admin"))) -> dict:
    if (
        id not in PARAMS
        or set(data.params) != PARAMS[id]
        or any(v <= 0 or v > 10080 for v in data.params.values())
    ):
        fail(
            422,
            "invalid_parameters",
            "Use exactly the built-in rule's positive numeric parameters.",
        )
    if id == "cdc_consecutive_failures" and (
        data.params["n"] != int(data.params["n"]) or data.params["n"] > 100
    ):
        fail(422, "invalid_parameters", "n must be an integer between 1 and 100.")
    with connection() as conn:
        for channel in data.channels:
            if not conn.execute(
                "SELECT 1 FROM obs.notification_channels WHERE channel_id=%s", (channel,)
            ).fetchone():
                fail(422, "invalid_channel", "Unknown notification channel.")
        rule = conn.execute(
            """UPDATE obs.alert_rules SET severity=%s,params=%s,enabled=%s,repeat_min=%s,channels=%s WHERE rule_id=%s RETURNING *""",
            (data.severity, Jsonb(data.params), data.enabled, data.repeat_min, data.channels, id),
        ).fetchone()
        audit(conn, user["email"], "update_alert_rule", id, data.model_dump())
    return rule


@router.post("/channels/{id}/test", response_model=s.Message)
def test_channel(id: str, user: dict = Depends(require_role("admin"))) -> dict:
    require_demo()
    if not one("SELECT 1 FROM obs.notification_channels WHERE channel_id=%s AND enabled", (id,)):
        fail(404, "channel_not_found", "Enabled channel not found.")
    with connection() as conn:
        deliver(conn, id, "test", "Observability Console · Test notification · Demo delivery")
        audit(conn, user["email"], "test_channel", id, {"simulated": True})
    return {"message": "Test notification recorded locally. Demo mode sends no external messages."}


@router.post("/onboarding/preflight", response_model=s.Preflight)
def preflight(data: s.OnboardInput, user: dict = Depends(require_role("operator"))) -> dict:
    result = run_preflight(data)
    with connection() as conn:
        audit(
            conn,
            user["email"],
            "onboarding_preflight",
            data.tenant_id,
            {"passed": result["passed"], "simulated": True},
        )
    return result


@router.post("/onboarding", response_model=s.OnboardProgress, status_code=201)
def onboard(data: s.OnboardInput, user: dict = Depends(require_role("operator"))) -> dict:
    return start(data, user["email"])


@router.patch("/users/{id}", response_model=s.Message)
def update_user(id: int, data: s.UserPatch, user: dict = Depends(require_role("admin"))) -> dict:
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110531)")
        target = conn.execute(
            "SELECT * FROM obs.users WHERE user_id=%s FOR UPDATE", (id,)
        ).fetchone()
        if not target:
            fail(404, "user_not_found", "User not found.")
        if target["role"] == "admin" and data.role != "admin":
            admins = conn.execute(
                "SELECT count(*) AS n FROM obs.users WHERE role='admin'"
            ).fetchone()["n"]
            if admins <= 1:
                fail(409, "last_admin", "Keep at least one administrator.")
        conn.execute("UPDATE obs.users SET role=%s WHERE user_id=%s", (data.role, id))
        audit(
            conn,
            user["email"],
            "update_user_role",
            str(id),
            {"role": data.role, "user": redact(target["email"])},
        )
    return {"message": "User role updated.", "simulated": False}
