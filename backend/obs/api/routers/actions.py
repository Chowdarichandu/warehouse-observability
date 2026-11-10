from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from psycopg.types.json import Jsonb

from obs.actions.retry import retry as retry_action
from obs.alerter.notify import deliver
from obs.alerter.rules import PARAMS
from obs.api import schemas as s
from obs.audit import audit
from obs.auth import (
    PERMISSIONS,
    SYSTEM_ROLE_PERMISSIONS,
    effective_permissions,
    fail,
    require_permission,
    require_role,
)
from obs.db import connection, notify, one
from obs.demo.scenarios import upsert_run
from obs.demo.seed import make_run
from obs.onboarding.preflight import preflight as run_preflight
from obs.onboarding.service import start
from obs.redact import redact
from obs.settings import settings

router = APIRouter(tags=["Audited actions"])


def _check_grantable(actor: dict, role: str, bundle: list[str]) -> None:
    actor_rights = effective_permissions(actor.get("role", ""), actor.get("permissions", []))
    if not effective_permissions(role, bundle).issubset(actor_rights):
        fail(403, "permission_escalation", "You cannot grant permissions beyond your own.")


def _target_bundle(conn, target: dict) -> list[str]:
    if target.get("role_name"):
        row = conn.execute(
            "SELECT permissions FROM obs.roles WHERE name=%s", (target["role_name"],)
        ).fetchone()
        return row["permissions"] if row and isinstance(row.get("permissions"), list) else []
    return SYSTEM_ROLE_PERMISSIONS.get(target.get("role"), [])


@router.post("/runs/{run_key}/retry", response_model=s.RetryResult)
def retry(
    run_key: str, user: dict = Depends(require_role("operator", "trigger_pipelines"))
) -> dict:
    return retry_action(run_key, user["email"])


@router.patch("/tenants/{id}", response_model=s.Message)
def update_tenant(
    id: str, data: s.TenantPatch, user: dict = Depends(require_role("admin", "manage_tenants"))
) -> dict:
    if settings().mode == "live":
        from obs.actions.live import enabled

        enabled()
        if data.status is not None and not settings().registry_dags_enabled:
            fail(
                409,
                "registry_not_enabled",
                "Deploy the registry-driven DAGs and enable REGISTRY_DAGS_ENABLED before pausing or resuming tenants.",
            )
    changes = data.model_dump(exclude_none=True)
    if not changes:
        fail(422, "empty_patch", "Supply at least one change.")
    with connection() as conn:
        tenant = conn.execute(
            "SELECT status FROM obs.tenants WHERE tenant_id=%s FOR UPDATE", (id,)
        ).fetchone()
        if not tenant:
            fail(404, "tenant_not_found", "Tenant not found.")
        if data.status is not None and tenant["status"] not in {"active", "paused"}:
            fail(409, "tenant_not_ready", "Complete onboarding before changing tenant status.")
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
    return {"message": "Tenant settings updated.", "simulated": settings().mode == "demo"}


@router.post("/tenants/{id}/resync", response_model=s.Message)
def resync(id: str, user: dict = Depends(require_role("admin", "manage_tenants"))) -> dict:
    if settings().mode != "demo":
        fail(403, "demo_only", "Simulated resync is available only in demo mode.")
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
def ack(id: int, user: dict = Depends(require_role("operator", "manage_alerts"))) -> dict:
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
def resolve(id: int, user: dict = Depends(require_role("operator", "manage_alerts"))) -> dict:
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
def update_rule(
    id: str, data: s.RulePatch, user: dict = Depends(require_role("admin", "manage_alerts"))
) -> dict:
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
def test_channel(id: str, user: dict = Depends(require_role("admin", "manage_alerts"))) -> dict:
    if not one("SELECT 1 FROM obs.notification_channels WHERE channel_id=%s AND enabled", (id,)):
        fail(404, "channel_not_found", "Enabled channel not found.")
    with connection() as conn:
        deliver(conn, id, "test", "Pravah · Test notification")
        audit(conn, user["email"], "test_channel", id, {"simulated": settings().mode == "demo"})
    return {
        "message": "Test notification recorded locally. Demo mode sends no external messages."
        if settings().mode == "demo"
        else "Test notification queued. Check delivery status in Administration.",
        "simulated": settings().mode == "demo",
    }


@router.post("/onboarding/preflight", response_model=s.Preflight)
def preflight(
    data: s.OnboardInput, user: dict = Depends(require_role("operator", "manage_tenants"))
) -> dict:
    result = run_preflight(data)
    with connection() as conn:
        audit(
            conn,
            user["email"],
            "onboarding_preflight",
            data.tenant_id,
            {"passed": result["passed"], "simulated": result["simulated"]},
        )
    return result


@router.post("/onboarding", response_model=s.OnboardProgress, status_code=201)
def onboard(
    data: s.OnboardInput, user: dict = Depends(require_role("operator", "manage_tenants"))
) -> dict:
    return start(data, user["email"])


@router.patch("/users/{id}", response_model=s.Message)
def update_user(
    id: int, data: s.UserPatch, user: dict = Depends(require_role("admin", "manage_users"))
) -> dict:
    if settings().auth_provider == "oidc":
        fail(
            403,
            "sso_managed_roles",
            "Manage roles through the configured identity provider groups.",
        )
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110531)")
        target = conn.execute(
            "SELECT * FROM obs.users WHERE user_id=%s FOR UPDATE", (id,)
        ).fetchone()
        if not target:
            fail(404, "user_not_found", "User not found.")
        new_role = data.role
        new_role_name = data.role_name
        if data.role_name:
            bundle = conn.execute(
                "SELECT * FROM obs.roles WHERE name=%s FOR SHARE", (data.role_name,)
            ).fetchone()
            if not bundle:
                fail(404, "role_not_found", "That role does not exist.")
            new_role = bundle["base_level"]
            granted_bundle = (
                bundle["permissions"] if isinstance(bundle["permissions"], list) else []
            )
        elif data.role is not None:
            new_role_name = None
            granted_bundle = SYSTEM_ROLE_PERMISSIONS.get(new_role, [])
        else:
            fail(422, "role_required", "Choose a role or a custom role bundle.")
        _check_grantable(user, new_role, granted_bundle)
        if target["role"] == "admin" and new_role != "admin":
            admins = conn.execute(
                "SELECT count(*) AS n FROM obs.users WHERE role='admin'"
            ).fetchone()["n"]
            if admins <= 1:
                fail(409, "last_admin", "Keep at least one administrator.")
        conn.execute(
            "UPDATE obs.users SET role=%s, role_name=%s WHERE user_id=%s",
            (new_role, new_role_name, id),
        )
        audit(
            conn,
            user["email"],
            "update_user_role",
            str(id),
            {"role": new_role, "role_name": new_role_name, "user": redact(target["email"])},
        )
    return {"message": "User role updated.", "simulated": False}


@router.post("/users", response_model=s.UserCreateResult)
def create_user(
    data: s.UserCreate, user: dict = Depends(require_role("admin", "manage_users"))
) -> dict:
    from obs.auth import hasher, temporary_password

    if settings().auth_provider == "oidc":
        fail(
            403,
            "sso_managed_roles",
            "Manage accounts through the configured identity provider.",
        )
    email = data.email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        fail(422, "invalid_email", "Enter a valid email address.")
    generated = None
    secret_value = data.initial_password
    if not secret_value:
        generated = temporary_password()
        secret_value = generated
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110531)")
        existing = conn.execute(
            "SELECT user_id FROM obs.users WHERE lower(email)=%s", (email,)
        ).fetchone()
        if existing:
            fail(409, "user_exists", "A user with that email already exists.")
        role = data.role
        role_name = None
        if data.role_name:
            bundle = conn.execute(
                "SELECT * FROM obs.roles WHERE name=%s FOR SHARE", (data.role_name,)
            ).fetchone()
            if not bundle:
                fail(404, "role_not_found", "That role does not exist.")
            role = bundle["base_level"]
            role_name = bundle["name"]
            granted_bundle = (
                bundle["permissions"] if isinstance(bundle["permissions"], list) else []
            )
        else:
            granted_bundle = SYSTEM_ROLE_PERMISSIONS.get(role, [])
        _check_grantable(user, role, granted_bundle)
        row = conn.execute(
            "INSERT INTO obs.users (email, display_name, role, role_name, password_hash)"
            " VALUES (%s,%s,%s,%s,%s) RETURNING user_id",
            (email, data.display_name.strip(), role, role_name, hasher.hash(secret_value)),
        ).fetchone()
        new_id = row["user_id"]
        audit(
            conn,
            user["email"],
            "create_user",
            str(new_id),
            {"role": role, "role_name": role_name, "user": redact(email)},
        )
    message = "User created."
    if generated:
        message += (
            " Share the temporary password with them;"
            " they can change it after signing in."
        )
    return {
        "message": message,
        "user_id": new_id,
        "temporary_password": generated,
        "simulated": settings().mode == "demo",
    }


@router.delete("/users/{id}", response_model=s.Message)
def delete_user(
    id: int, user: dict = Depends(require_role("admin", "manage_users"))
) -> dict:
    if settings().auth_provider == "oidc":
        fail(
            403,
            "sso_managed_roles",
            "Manage accounts through the configured identity provider.",
        )
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110531)")
        target = conn.execute(
            "SELECT * FROM obs.users WHERE user_id=%s FOR UPDATE", (id,)
        ).fetchone()
        if not target:
            fail(404, "user_not_found", "User not found.")
        if target["email"].lower() == str(user.get("email", "")).lower():
            fail(409, "cannot_delete_self", "You cannot remove your own account.")
        if target["role"] == "admin":
            admins = conn.execute(
                "SELECT count(*) AS n FROM obs.users WHERE role='admin'"
            ).fetchone()["n"]
            if admins <= 1:
                fail(409, "last_admin", "Keep at least one administrator.")
        conn.execute("DELETE FROM obs.sessions WHERE user_id=%s", (id,))
        conn.execute("DELETE FROM obs.users WHERE user_id=%s", (id,))
        audit(
            conn,
            user["email"],
            "delete_user",
            str(id),
            {"user": redact(target["email"])},
        )
    return {"message": "User removed.", "simulated": False}


@router.get("/roles", response_model=list[s.RoleOut])
def list_roles(user: dict = Depends(require_permission("manage_users"))) -> list:
    rows = []
    with connection() as conn:
        custom = conn.execute("SELECT * FROM obs.roles ORDER BY name").fetchall()
    for name in ("viewer", "operator", "admin"):
        rows.append(
            {
                "name": name,
                "base_level": name,
                "permissions": SYSTEM_ROLE_PERMISSIONS[name],
                "description": "Built-in role",
                "system": True,
                "created_by": None,
            }
        )
    for row in custom:
        rows.append(
            {
                "name": row["name"],
                "base_level": row["base_level"],
                "permissions": row["permissions"] if isinstance(row["permissions"], list) else [],
                "description": row["description"],
                "system": False,
                "created_by": row["created_by"],
            }
        )
    return rows


@router.post("/roles", response_model=s.RoleOut, status_code=201)
def create_role(data: s.RoleIn, user: dict = Depends(require_permission("manage_users"))) -> dict:
    name = data.name.strip()
    if name.lower() in SYSTEM_ROLE_PERMISSIONS:
        fail(409, "reserved_role", "That name is a built-in role.")
    permissions = [p for p in dict.fromkeys(data.permissions) if p in PERMISSIONS]
    if "view_console" not in permissions:
        permissions.insert(0, "view_console")
    _check_grantable(user, data.base_level, permissions)
    with connection() as conn:
        if conn.execute("SELECT 1 FROM obs.roles WHERE name=%s", (name,)).fetchone():
            fail(409, "role_exists", "A role with this name already exists.")
        conn.execute(
            "INSERT INTO obs.roles(name,base_level,permissions,description,created_by) VALUES(%s,%s,%s,%s,%s)",
            (name, data.base_level, Jsonb(permissions), data.description, user["email"]),
        )
        audit(conn, user["email"], "create_role", name, {"base_level": data.base_level})
    return {
        "name": name,
        "base_level": data.base_level,
        "permissions": permissions,
        "description": data.description,
        "system": False,
        "created_by": user["email"],
    }


@router.delete("/roles/{name}", response_model=s.Message)
def delete_role(name: str, user: dict = Depends(require_permission("manage_users"))) -> dict:
    if name in SYSTEM_ROLE_PERMISSIONS:
        fail(409, "reserved_role", "Built-in roles cannot be deleted.")
    with connection() as conn:
        if not conn.execute("SELECT 1 FROM obs.roles WHERE name=%s FOR UPDATE", (name,)).fetchone():
            fail(404, "role_not_found", "That role does not exist.")
        if conn.execute("SELECT 1 FROM obs.users WHERE role_name=%s LIMIT 1", (name,)).fetchone():
            fail(409, "role_in_use", "Reassign users before deleting this role.")
        conn.execute("DELETE FROM obs.roles WHERE name=%s", (name,))
        audit(conn, user["email"], "delete_role", name)
    return {"message": f"Role {name} deleted.", "simulated": False}


@router.post("/users/{id}/reset-password", response_model=s.PasswordResetResult)
def reset_password(id: int, user: dict = Depends(require_permission("manage_users"))) -> dict:
    from obs.auth import hasher, temporary_password

    if settings().auth_provider == "oidc":
        fail(409, "sso_managed", "Passwords are managed by the identity provider.")
    temporary = temporary_password()
    with connection() as conn:
        target = conn.execute(
            "SELECT * FROM obs.users WHERE user_id=%s FOR UPDATE", (id,)
        ).fetchone()
        if not target:
            fail(404, "user_not_found", "User not found.")
        _check_grantable(user, target["role"], _target_bundle(conn, target))
        conn.execute(
            "UPDATE obs.users SET password_hash=%s WHERE user_id=%s",
            (hasher.hash(temporary), id),
        )
        conn.execute(
            "UPDATE obs.sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL",
            (id,),
        )
        audit(conn, user["email"], "reset_password", str(id), {"user": redact(target["email"])})
    return {
        "message": "Password reset. Share the temporary password with the user; they can change it after signing in.",
        "temporary_password": temporary,
        "simulated": settings().mode == "demo",
    }


@router.post("/operations/{id}/reconcile", response_model=s.Message)
def reconcile(
    id: str,
    data: s.OperationResolution,
    user: dict = Depends(require_role("admin", "manage_platform")),
) -> dict:
    with connection() as conn:
        operation = conn.execute(
            "SELECT * FROM obs.operations WHERE id=%s FOR UPDATE", (id,)
        ).fetchone()
        if not operation:
            fail(404, "operation_not_found", "Operation not found.")
        if operation["status"] == "sending" and operation["updated_at"] > datetime.now(
            UTC
        ) - timedelta(minutes=5):
            fail(
                409,
                "operation_in_progress",
                "Wait for the in-flight request to finish before reviewing its outcome.",
            )
        if operation["status"] not in {"failed", "uncertain", "sending"}:
            fail(409, "operation_final", "Only unconfirmed operations can be reconciled.")
        conn.execute(
            "UPDATE obs.operations SET status=%s,last_error=%s,updated_at=now() WHERE id=%s",
            (data.status, redact(data.note), id),
        )
        # Confirmed failure permits a new explicit operator request with a fresh key.
        if data.status == "failed":
            conn.execute(
                "UPDATE obs.operations SET idempotency_key=idempotency_key||':reviewed:'||id WHERE id=%s",
                (id,),
            )
        audit(conn, user["email"], "reconcile_operation", id, data.model_dump())
    return {"message": "Operation reconciled. No upstream action was sent.", "simulated": False}


@router.post("/users/{id}/revoke-sessions", response_model=s.Message)
def revoke_sessions(id: int, user: dict = Depends(require_role("admin", "manage_users"))) -> dict:
    with connection() as conn:
        if not conn.execute("SELECT 1 FROM obs.users WHERE user_id=%s", (id,)).fetchone():
            fail(404, "user_not_found", "User not found.")
        conn.execute(
            "UPDATE obs.sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL",
            (id,),
        )
        audit(conn, user["email"], "revoke_sessions", str(id))
    return {"message": "All existing sessions for this user were revoked.", "simulated": False}


ANALYTICS_DAGS = [
    {"id": "analytics_marts", "name": "Analytics marts build"},
    {"id": "analytics_rollup", "name": "KPI rollup"},
    {"id": "analytics_quality", "name": "Analytics quality checks"},
]
PIPELINE_DAGS = {
    "mysql_initial": ("mysql", "initial", "MySQL initial load"),
    "mongo_initial": ("mongo", "initial", "MongoDB initial load"),
    "mysql_cdc": ("mysql", "cdc", "MySQL CDC sync"),
    "mongo_cdc": ("mongo", "cdc", "MongoDB CDC sync"),
}


def _latest_run(conn, tenant: str, source: str, load: str):
    return conn.execute(
        """SELECT status, started_at FROM obs.pipeline_runs
           WHERE tenant_id=%s AND source_type=%s AND load_type=%s
           ORDER BY started_at DESC NULLS LAST LIMIT 1""",
        (tenant, source, load),
    ).fetchone()


def _initial_done(conn, tenant: str, source: str) -> bool:
    return bool(
        conn.execute(
            """SELECT 1 FROM obs.pipeline_runs
               WHERE tenant_id=%s AND source_type=%s AND load_type='initial' AND status='success' LIMIT 1""",
            (tenant, source),
        ).fetchone()
    )


def _iso(value):
    return value.isoformat() if value else None


@router.get("/tenants/{id}/workflow", response_model=s.WorkflowState)
def workflow(id: str, user: dict = Depends(require_permission("view_console"))) -> dict:
    with connection() as conn:
        tenant = conn.execute("SELECT * FROM obs.tenants WHERE tenant_id=%s", (id,)).fetchone()
        if not tenant:
            fail(404, "tenant_not_found", "Tenant not found.")
        sources = []
        for source in ("mysql", "mongo"):
            if not tenant[f"has_{source}"]:
                continue
            initial = _latest_run(conn, id, source, "initial")
            cdc = _latest_run(conn, id, source, "cdc")
            sources.append(
                {
                    "source": source,
                    "initial_status": initial["status"] if initial else "not_started",
                    "cdc_status": (
                        cdc["status"]
                        if cdc
                        else ("ready" if _initial_done(conn, id, source) else "locked")
                    ),
                    "last_initial_at": _iso(initial["started_at"]) if initial else None,
                    "last_cdc_at": _iso(cdc["started_at"]) if cdc else None,
                }
            )
        eligible = bool(tenant["has_mysql"]) and _initial_done(conn, id, "mysql")
        analytics = []
        for dag in ANALYTICS_DAGS:
            event = conn.execute(
                """SELECT status, at FROM obs.tenant_events
                   WHERE tenant_id=%s AND step=%s ORDER BY at DESC LIMIT 1""",
                (id, f"analytics:{dag['id']}"),
            ).fetchone()
            analytics.append(
                {
                    "id": dag["id"],
                    "name": dag["name"],
                    "last_status": event["status"] if event else None,
                    "last_at": _iso(event["at"]) if event else None,
                }
            )
    return {
        "tenant_id": id,
        "sources": sources,
        "analytics_eligible": eligible,
        "analytics": analytics,
    }


@router.post("/tenants/{id}/trigger", response_model=s.Message)
def trigger(
    id: str, data: s.TriggerIn, user: dict = Depends(require_permission("trigger_pipelines"))
) -> dict:
    if settings().mode != "demo":
        fail(422, "demo_only", "Manual DAG triggers are available in demo mode.")
    dag = data.dag
    with connection() as conn:
        tenant = conn.execute("SELECT * FROM obs.tenants WHERE tenant_id=%s", (id,)).fetchone()
        if not tenant:
            fail(404, "tenant_not_found", "Tenant not found.")
        if dag in PIPELINE_DAGS:
            fail(
                403,
                "manual_trigger_disabled",
                "Source pipelines are controlled by onboarding and cannot be triggered here.",
            )
        elif dag in {d["id"] for d in ANALYTICS_DAGS}:
            label = next(d["name"] for d in ANALYTICS_DAGS if d["id"] == dag)
            source, load = None, "analytics"
            if not (tenant["has_mysql"] and _initial_done(conn, id, "mysql")):
                fail(
                    422,
                    "analytics_locked",
                    "Analytics unlocks once the MySQL initial load completes.",
                )
        else:
            fail(404, "dag_not_found", "Unknown DAG.")
        job_key = f"trigger:{id}:{dag}:{int(datetime.now(UTC).timestamp())}"
        conn.execute(
            "INSERT INTO obs.demo_jobs(job_key,kind,tenant_id,payload) VALUES(%s,'trigger',%s,%s)",
            (
                job_key,
                id,
                Jsonb({"dag": dag, "source": source, "load": load, "label": label}),
            ),
        )
        conn.execute(
            "INSERT INTO obs.tenant_events(tenant_id,step,status,message) VALUES(%s,%s,'started',%s)",
            (
                id,
                f"analytics:{dag}" if load == "analytics" else label,
                f"Triggered by {user['email']}",
            ),
        )
        audit(conn, user["email"], "trigger_dag", id, {"dag": dag})
    return {"message": f"{label} triggered for {id}.", "simulated": True}
