from fastapi import APIRouter, Depends, Query
from psycopg.errors import LockNotAvailable, UniqueViolation
from psycopg.types.json import Jsonb

from obs.audit import audit
from obs.auth import current_user, fail, require_role
from obs.db import connection, notify
from obs.quality.engine import execute
from obs.quality.models import (
    QualityCheck,
    QualityCheckInput,
    QualityCheckPage,
    QualityCheckPatch,
    QualityResult,
    QualityResultPage,
)
from obs.redact import redact_tree
from obs.settings import settings

router = APIRouter(tags=["Data quality"])


def write_enabled() -> None:
    if settings().mode == "live" and not settings().live_actions_enabled:
        fail(403, "live_actions_disabled", "Enable reviewed live actions before changing checks.")


def tenant_exists(conn, tenant_id: str) -> None:
    tenant = conn.execute(
        "SELECT warehouse_schema FROM obs.tenants WHERE tenant_id=%s AND status<>'offboarded'",
        (tenant_id,),
    ).fetchone()
    if not tenant:
        fail(404, "tenant_not_found", "Registered tenant not found.")
    if settings().mode == "live" and not tenant["warehouse_schema"]:
        fail(422, "warehouse_schema_missing", "Configure the tenant's warehouse schema first.")


@router.get("/quality/checks", response_model=QualityCheckPage)
def checks(
    tenant_id: str | None = None, page: int = Query(1, ge=1), user: dict = Depends(current_user)
) -> dict:
    with connection() as conn:
        where, args = ("WHERE q.tenant_id=%s", [tenant_id]) if tenant_id else ("", [])
        total = conn.execute(
            f"SELECT count(*) AS n FROM obs.quality_checks q {where}", args
        ).fetchone()["n"]
        items = conn.execute(
            f"""SELECT q.*,to_jsonb(r) AS latest_result FROM obs.quality_checks q LEFT JOIN LATERAL
            (SELECT * FROM obs.quality_results WHERE check_id=q.id AND checked_at>=q.updated_at ORDER BY checked_at DESC,id DESC LIMIT 1) r ON true
            {where} ORDER BY q.tenant_id,q.name LIMIT 25 OFFSET %s""",
            [*args, (page - 1) * 25],
        ).fetchall()
    return redact_tree({"items": items, "total": total})


@router.post("/quality/checks", response_model=QualityCheck, status_code=201)
def create(data: QualityCheckInput, user: dict = Depends(require_role("admin"))) -> dict:
    write_enabled()
    try:
        with connection() as conn:
            tenant_exists(conn, data.tenant_id)
            item = conn.execute(
                """INSERT INTO obs.quality_checks(tenant_id,name,table_name,kind,params,sample_limit,interval_sec,enabled)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (
                    data.tenant_id,
                    data.name,
                    data.table_name,
                    data.kind,
                    Jsonb(data.params),
                    data.sample_limit,
                    data.interval_sec,
                    data.enabled,
                ),
            ).fetchone()
            audit(
                conn,
                user["email"],
                "quality_check_created",
                str(item["id"]),
                {"tenant_id": data.tenant_id, "kind": data.kind},
            )
            notify(conn, "quality.updated", {"tenant_id": data.tenant_id, "status": "configured"})
            return redact_tree(item)
    except UniqueViolation:
        fail(409, "quality_name_exists", "A check with this name already exists for this tenant.")


@router.put("/quality/checks/{id}", response_model=QualityCheck)
def update(id: int, data: QualityCheckInput, user: dict = Depends(require_role("admin"))) -> dict:
    write_enabled()
    try:
        with connection() as conn:
            existing = conn.execute(
                "SELECT * FROM obs.quality_checks WHERE id=%s FOR UPDATE", (id,)
            ).fetchone()
            if not existing:
                fail(404, "quality_not_found", "Quality check not found.")
            if existing["tenant_id"] != data.tenant_id:
                fail(422, "tenant_immutable", "A check cannot be moved to another tenant.")
            tenant_exists(conn, data.tenant_id)
            item = conn.execute(
                """UPDATE obs.quality_checks SET name=%s,table_name=%s,kind=%s,params=%s,sample_limit=%s,interval_sec=%s,enabled=%s,updated_at=now(),last_checked_at=NULL
                WHERE id=%s RETURNING *""",
                (
                    data.name,
                    data.table_name,
                    data.kind,
                    Jsonb(data.params),
                    data.sample_limit,
                    data.interval_sec,
                    data.enabled,
                    id,
                ),
            ).fetchone()
            audit(
                conn,
                user["email"],
                "quality_check_updated",
                str(id),
                {"tenant_id": data.tenant_id, "kind": data.kind},
            )
            notify(conn, "quality.updated", {"tenant_id": data.tenant_id, "status": "configured"})
            return redact_tree(item)
    except UniqueViolation:
        fail(409, "quality_name_exists", "A check with this name already exists for this tenant.")


@router.patch("/quality/checks/{id}", response_model=QualityCheck)
def toggle(id: int, data: QualityCheckPatch, user: dict = Depends(require_role("admin"))) -> dict:
    write_enabled()
    with connection() as conn:
        item = conn.execute(
            "UPDATE obs.quality_checks SET enabled=%s WHERE id=%s RETURNING *",
            (data.enabled, id),
        ).fetchone()
        if not item:
            fail(404, "quality_not_found", "Quality check not found.")
        audit(
            conn,
            user["email"],
            "quality_check_enabled" if data.enabled else "quality_check_disabled",
            str(id),
            {"tenant_id": item["tenant_id"]},
        )
        notify(conn, "quality.updated", {"tenant_id": item["tenant_id"], "status": "configured"})
        return redact_tree(item)


@router.post("/quality/checks/{id}/run", response_model=QualityResult)
def run(id: int, user: dict = Depends(require_role("operator"))) -> dict:
    write_enabled()
    if settings().mode == "live" and not settings().quality_enabled:
        fail(
            403,
            "quality_disabled",
            "Enable QUALITY_ENABLED after reviewing warehouse read permissions.",
        )
    try:
        with connection() as conn:
            item = conn.execute(
                "SELECT * FROM obs.quality_checks WHERE id=%s FOR UPDATE NOWAIT", (id,)
            ).fetchone()
            if not item:
                fail(404, "quality_not_found", "Quality check not found.")
            if not item["enabled"]:
                fail(409, "quality_disabled", "Enable this check before running it.")
            result = execute(conn, item)
            audit(
                conn,
                user["email"],
                "quality_check_run",
                str(id),
                {
                    "tenant_id": item["tenant_id"],
                    "result": result["status"],
                    "simulated": result["simulated"],
                },
            )
            return redact_tree(result)
    except LockNotAvailable:
        fail(
            409, "quality_busy", "This check is already running or being edited. Try again shortly."
        )


@router.get("/quality/results", response_model=QualityResultPage)
def results(
    tenant_id: str | None = None,
    check_id: int | None = None,
    page: int = Query(1, ge=1),
    user: dict = Depends(current_user),
) -> dict:
    conditions, args = [], []
    if tenant_id:
        conditions.append("tenant_id=%s")
        args.append(tenant_id)
    if check_id is not None:
        conditions.append("check_id=%s")
        args.append(check_id)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    with connection() as conn:
        total = conn.execute(
            f"SELECT count(*) AS n FROM obs.quality_results {where}", args
        ).fetchone()["n"]
        items = conn.execute(
            f"SELECT * FROM obs.quality_results {where} ORDER BY checked_at DESC,id DESC LIMIT 25 OFFSET %s",
            [*args, (page - 1) * 25],
        ).fetchall()
    return redact_tree({"items": items, "total": total})
