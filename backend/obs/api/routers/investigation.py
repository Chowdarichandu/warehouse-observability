"""Personal investigation views and a bounded, redacted operational timeline."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from obs.api.schemas import Message
from obs.audit import audit
from obs.auth import current_user, fail, require_role
from obs.db import connection, one, rows
from obs.redact import redact, redact_tree
from obs.repositories.analytics import bounds
from obs.repositories.runs import detail

router = APIRouter(tags=["Investigation"], dependencies=[Depends(current_user)])
FILTERS = {
    "tenant",
    "status",
    "source",
    "load",
    "stage",
    "error_class",
    "q",
    "sort",
    "range",
    "from",
    "to",
}


class SavedViewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    filters: dict[str, str]

    @model_validator(mode="after")
    def valid_filters(self) -> "SavedViewInput":
        self.name = redact(self.name.strip())
        if not self.name or self.filters.keys() - FILTERS:
            raise ValueError("Choose a name and supported run filters.")
        if any(len(v) > 500 for v in self.filters.values()):
            raise ValueError("Filter values must be at most 500 characters.")
        choices = {
            "status": {"success", "failed", "running", "queued", "cancelled", "skipped"},
            "source": {"mysql", "mongo"},
            "load": {"initial", "cdc"},
            "stage": {"airflow", "airbyte", "warehouse"},
            "range": {"1h", "6h", "24h", "7d", "30d", "custom"},
            "sort": {
                f"{prefix}{key}"
                for prefix in ("", "-")
                for key in (
                    "started_at",
                    "duration_s",
                    "tenant_id",
                    "status",
                    "rows_synced",
                    "queue_delay_s",
                )
            },
        }
        for key, values in choices.items():
            if self.filters.get(key) and self.filters[key] not in values:
                raise ValueError(f"Unsupported {key} filter.")
        if self.filters.get("range") == "custom" or "from" in self.filters or "to" in self.filters:
            start = datetime.fromisoformat(self.filters.get("from", "").replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.filters.get("to", "").replace("Z", "+00:00"))
            if start.tzinfo is None or end.tzinfo is None:
                raise ValueError("Custom bounds require a timezone.")
            bounds("custom", start, end)
        self.filters = redact_tree({k: v for k, v in self.filters.items() if v})
        return self


class SavedView(BaseModel):
    id: int
    name: str
    filters: dict[str, str]
    created_at: datetime


class SavedViews(BaseModel):
    items: list[SavedView]


@router.get("/saved-views", response_model=SavedViews)
def saved_views(user: dict = Depends(current_user)) -> dict:
    return {
        "items": redact_tree(
            rows(
                "SELECT id,name,filters,created_at FROM obs.saved_views WHERE user_id=%s ORDER BY name,id",
                (user["user_id"],),
            )
        )
    }


@router.post("/saved-views", response_model=SavedView, status_code=201)
def save_view(body: SavedViewInput, user: dict = Depends(require_role("viewer"))) -> dict:
    try:
        with connection() as conn:
            # Serialize the per-user bound across simultaneous requests.
            conn.execute("SELECT pg_advisory_xact_lock(7841,%s)", (user["user_id"],))
            if (
                conn.execute(
                    "SELECT count(*) AS n FROM obs.saved_views WHERE user_id=%s", (user["user_id"],)
                ).fetchone()["n"]
                >= 30
            ):
                fail(
                    409, "view_limit", "Remove an existing view before saving another (maximum 30)."
                )
            result = conn.execute(
                "INSERT INTO obs.saved_views(user_id,name,filters) VALUES(%s,%s,%s) RETURNING id,name,filters,created_at",
                (user["user_id"], body.name, Jsonb(body.filters)),
            ).fetchone()
            audit(conn, user["email"], "view.save", str(result["id"]), {"name": body.name})
        return result
    except UniqueViolation:
        fail(409, "duplicate_view", "A saved view already uses that name.")


@router.delete("/saved-views/{view_id}", response_model=Message)
def delete_view(view_id: int, user: dict = Depends(require_role("viewer"))) -> dict:
    with connection() as conn:
        removed = conn.execute(
            "DELETE FROM obs.saved_views WHERE id=%s AND user_id=%s RETURNING id",
            (view_id, user["user_id"]),
        ).fetchone()
        if not removed:
            fail(404, "view_not_found", "Saved view not found.")
        audit(conn, user["email"], "view.delete", str(view_id))
    return {"message": "Saved view removed."}


class InvestigationEvent(BaseModel):
    id: str
    kind: Literal["run", "alert", "onboarding", "action", "quality"]
    title: str
    status: str
    at: datetime
    tenant_id: str | None = None
    run_key: str | None = None


class InvestigationTimeline(BaseModel):
    items: list[InvestigationEvent]
    truncated: bool
    note: str = "Run events and tenant context, ordered by recorded time. Tenant alerts and checks may concern other runs."


@router.get("/investigation/timeline", response_model=InvestigationTimeline)
def timeline(
    tenant: str = "",
    run_key: str = "",
    range: str = "24h",
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
) -> dict:
    start, end = bounds(range, from_, to)
    if run_key:
        run = detail(run_key)["run"]
        tenant = run["tenant_id"]
    if tenant and not one("SELECT 1 FROM obs.tenants WHERE tenant_id=%s", (tenant,)):
        fail(404, "tenant_not_found", "Tenant not found.")
    result = rows(
        """
        WITH events AS (
          SELECT 'run:'||r.run_key||':'||v.phase AS id,'run' AS kind,
            r.source_type||' '||r.load_type||' · '||v.phase AS title,
            CASE WHEN v.phase='ended' THEN r.status ELSE v.phase END AS status,
            v.at,r.tenant_id,r.run_key
          FROM obs.pipeline_runs r CROSS JOIN LATERAL
            (VALUES('queued',r.queued_at),('started',r.started_at),('ended',r.ended_at)) v(phase,at)
          WHERE (%s='' OR r.tenant_id=%s) AND (%s='' OR r.run_key=%s)
            AND v.at>=%s AND v.at<%s
          UNION ALL
          SELECT 'alert:'||a.id||':'||v.phase,'alert',a.title,v.phase,v.at,a.tenant_id,NULL
          FROM obs.alerts a CROSS JOIN LATERAL
            (VALUES('firing',a.first_fired_at),('acked',a.acked_at),('resolved',a.resolved_at)) v(phase,at)
          WHERE (%s='' OR a.tenant_id=%s) AND v.at>=%s AND v.at<%s
          UNION ALL
          SELECT 'onboard:'||id,'onboarding',step||' · '||coalesce(message,''),status,at,tenant_id,NULL
          FROM obs.tenant_events WHERE (%s='' OR tenant_id=%s) AND at>=%s AND at<%s
          UNION ALL
          SELECT 'action:'||o.id,'action',o.kind,o.status,o.updated_at,coalesce(r.tenant_id,t.tenant_id),r.run_key
          FROM obs.operations o LEFT JOIN obs.pipeline_runs r ON o.target=r.run_key
          LEFT JOIN obs.tenants t ON o.target=t.tenant_id AND o.kind='onboard'
          WHERE (r.run_key IS NOT NULL OR t.tenant_id IS NOT NULL)
            AND (%s='' OR coalesce(r.tenant_id,t.tenant_id)=%s) AND (%s='' OR r.run_key=%s)
            AND o.updated_at>=%s AND o.updated_at<%s
          UNION ALL
          SELECT 'quality:'||r.id,'quality',q.name||' · '||q.table_name,r.status,r.checked_at,r.tenant_id,NULL
          FROM obs.quality_results r JOIN obs.quality_checks q ON q.id=r.check_id
          WHERE (%s='' OR r.tenant_id=%s) AND r.checked_at>=%s AND r.checked_at<%s
        ) SELECT * FROM events ORDER BY at DESC,id LIMIT 201
        """,
        (
            tenant,
            tenant,
            run_key,
            run_key,
            start,
            end,
            tenant,
            tenant,
            start,
            end,
            tenant,
            tenant,
            start,
            end,
            tenant,
            tenant,
            run_key,
            run_key,
            start,
            end,
            tenant,
            tenant,
            start,
            end,
        ),
    )
    return {"items": redact_tree(result[:200]), "truncated": len(result) > 200}
