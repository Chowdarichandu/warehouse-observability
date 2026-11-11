import csv
import io
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from obs.api import schemas as s
from obs.auth import current_user, fail, require_role
from obs.db import one, rows
from obs.redact import redact, redact_tree
from obs.repositories import analytics as a
from obs.repositories import runs as r

router = APIRouter(dependencies=[Depends(current_user)], tags=["Console"])
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]


@router.get("/overview", response_model=s.Overview)
def overview(
    range: str = "24h",
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
) -> dict:
    return a.overview(*a.bounds(range, from_, to))


@router.get("/metrics/overview", response_model=s.MetricsOverview)
def metrics_overview(
    range: str = "24h",
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
) -> dict:
    """Return aggregate dashboard metrics without run-level or platform detail."""
    data = a.overview(*a.bounds(range, from_, to), include_detail=False)
    return {
        "kpis": data["kpis"],
        "series": data["series"],
        "durations": data["durations"],
        "as_of": data["as_of"],
    }


@router.get("/metrics/tenants", response_model=s.Page[s.MetricsTenant])
def metrics_tenants(page: PageNumber = 1, page_size: PageSize = 25) -> dict:
    """Expose tenant labels and metric summaries, excluding run identifiers and logs."""
    items = []
    for tenant in a.tenants():
        items.append(
            {
                "tenant_id": tenant["tenant_id"],
                "display_name": tenant["display_name"],
                "health": tenant["health"],
                "freshness_sla_min": tenant["freshness_sla_min"],
                "failures_24h": tenant["failures_24h"],
                "worst_stale_min": tenant["worst_stale_min"],
                "sla_compliance": tenant["sla_compliance"],
                "avg_duration_min": tenant["avg_duration_min"],
                "last_success_at": tenant["last_success_at"],
                "pipeline_statuses": [
                    {
                        "source_type": run["source_type"],
                        "load_type": run["load_type"],
                        "status": run["status"],
                    }
                    for run in tenant["latest_runs"]
                ],
            }
        )
    return a.page(items, page, page_size)


@router.get("/tenants", response_model=s.Page[s.Tenant])
def tenants(q: str = "", health: str = "", page: PageNumber = 1, page_size: PageSize = 25) -> dict:
    items = [
        t
        for t in a.tenants()
        if q.lower() in (t["display_name"] + t["tenant_id"]).lower()
        and (not health or t["health"] == health)
    ]
    return a.page(items, page, page_size)


@router.get("/tenants/{id}", response_model=s.TenantDetail)
def tenant_detail(id: str) -> dict:
    config = one("SELECT * FROM obs.tenants WHERE tenant_id=%s", (id,))
    if not config:
        fail(404, "tenant_not_found", "Tenant not found.")
    return {
        # The owner email is workspace-internal data (the users list shows
        # emails too); redacting it here leaked a "[EMAIL]" placeholder into
        # the Connections panel and starved the settings form of its value.
        "config": config,
        "health": next(t for t in a.tenants() if t["tenant_id"] == id),
        "tables": rows(
            "SELECT DISTINCT ON(table_name) * FROM obs.warehouse_snapshots WHERE tenant_id=%s ORDER BY table_name,checked_at DESC",
            (id,),
        ),
        "alerts": redact_tree(
            rows(
                "SELECT * FROM obs.alerts WHERE tenant_id=%s AND state<>'resolved' ORDER BY first_fired_at DESC LIMIT 100",
                (id,),
            )
        ),
        "events": rows(
            "SELECT * FROM obs.tenant_events WHERE tenant_id=%s ORDER BY at LIMIT 100", (id,)
        ),
        "errors": redact_tree(
            rows(
                "SELECT * FROM obs.run_errors WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 10",
                (id,),
            )
        ),
        "schema_changes": [c for c in a.schema_changes() if c["tenant_id"] == id],
        "baselines": rows(
            """SELECT source_type,load_type,percentile_cont(.5) WITHIN GROUP(ORDER BY duration_s) AS median_s
            FROM obs.pipeline_runs WHERE tenant_id=%s AND status='success' AND started_at>now()-interval '7 days'
            GROUP BY source_type,load_type""",
            (id,),
        ),
    }


@router.get("/tenants/{id}/timeline", response_model=s.Page[s.Run])
def timeline(
    id: str,
    range: str = "24h",
    page: PageNumber = 1,
    page_size: PageSize = 200,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
) -> dict:
    if not one("SELECT 1 FROM obs.tenants WHERE tenant_id=%s", (id,)):
        fail(404, "tenant_not_found", "Tenant not found.")
    return r.list_runs(*a.bounds(range, from_, to), tenant=id, page=page, page_size=page_size)


@router.get(
    "/runs",
    response_model=s.Page[s.Run],
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
def runs(
    tenant: str = "",
    status: str = "",
    source: str = "",
    load: str = "",
    stage: str = "",
    error_class: str = "",
    q: str = "",
    range: str = "24h",
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 25,
    sort: str = "-started_at",
    format: Literal["json", "csv"] = "json",
) -> dict | Response:
    result = r.list_runs(
        *a.bounds(range, from_, to),
        tenant=tenant,
        status=status,
        source=source,
        load=load,
        stage=stage,
        error_class=error_class,
        q=q,
        page=page,
        page_size=page_size,
        sort=sort,
        export=format == "csv",
    )
    if format == "csv":
        output = io.StringIO()
        fields = [
            "run_key",
            "tenant_id",
            "source_type",
            "load_type",
            "status",
            "failed_stage",
            "started_at",
            "ended_at",
            "duration_s",
            "queue_delay_s",
            "rows_synced",
            "error_class",
        ]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in result["items"]:
            # Prevent formula injection when a spreadsheet opens an exported value.
            writer.writerow(
                {
                    k: ("'" + str(v) if str(v).startswith(("=", "+", "-", "@")) else v)
                    for k, v in item.items()
                }
            )
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=runs.csv"},
        )
    return result


@router.get("/tenants/{id}/metrics", response_model=s.TenantMetrics)
def tenant_metrics(
    id: str,
    range: str = "24h",
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
) -> dict:
    """Duration and queue aggregates over EVERY run in the range.

    The tenant page used to derive these from the latest-200 timeline page,
    so initial loads silently vanished once CDC runs filled the page. This
    endpoint aggregates the full range in SQL instead.
    """
    if not one("SELECT 1 FROM obs.tenants WHERE tenant_id=%s", (id,)):
        fail(404, "tenant_not_found", "Tenant not found.")
    start, end = a.bounds(range, from_, to)
    pipelines = rows(
        """SELECT source_type, load_type,
                  count(*) FILTER (WHERE status='success' AND duration_s IS NOT NULL) AS runs,
                  avg(duration_s) FILTER (WHERE status='success') AS avg_s,
                  percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_s)
                      FILTER (WHERE status='success') AS p95_s,
                  avg(queue_delay_s) AS queue_avg_s,
                  percentile_cont(0.95) WITHIN GROUP (ORDER BY queue_delay_s) AS queue_p95_s
           FROM obs.pipeline_runs
           WHERE tenant_id=%s AND started_at>=%s AND started_at<%s
           GROUP BY source_type, load_type
           ORDER BY source_type, load_type""",
        (id, start, end),
    )
    bucket_hours = 1 if end - start <= timedelta(hours=48) else 6
    hourly = rows(
        """SELECT to_timestamp(floor(extract(epoch FROM started_at) / %s) * %s) AS bucket,
                  source_type, load_type, avg(duration_s) AS avg_s
           FROM obs.pipeline_runs
           WHERE tenant_id=%s AND started_at>=%s AND started_at<%s
             AND status='success' AND duration_s IS NOT NULL
           GROUP BY bucket, source_type, load_type
           ORDER BY bucket""",
        (bucket_hours * 3600, bucket_hours * 3600, id, start, end),
    )
    activity = rows(
        """SELECT date_trunc('hour', started_at) AS bucket,
                  count(*) FILTER (WHERE status='success') AS success,
                  count(*) FILTER (WHERE status='failed') AS failed,
                  count(*) FILTER (WHERE status='running') AS running
           FROM obs.pipeline_runs
           WHERE tenant_id=%s AND started_at>=%s AND started_at<%s
           GROUP BY bucket
           ORDER BY bucket""",
        (id, start, end),
    )
    return {"pipelines": pipelines, "hourly": hourly, "activity": activity}


@router.get("/runs/{run_key}/log", response_model=s.Log)
def log(run_key: str) -> dict:
    run = r.detail(run_key)["run"]
    stored = one("SELECT source,content FROM obs.run_logs WHERE run_key=%s", (run_key,))
    if not stored:
        from obs.settings import settings

        if settings().mode == "live":
            from obs.collector.normalize import failure
            from obs.integrations.airbyte import Airbyte
            from obs.integrations.airflow import Airflow

            if run.get("dag_id"):
                stored = {"source": "airflow", "content": Airflow().log(run)}
            elif run.get("airbyte_job_id"):
                _, _, content, _ = failure(Airbyte().job(run["airbyte_job_id"]))
                stored = {
                    "source": "airbyte",
                    "content": content
                    or "This Airbyte API does not expose attempt logs. Configure AIRBYTE_CONFIG_URL for OSS diagnostics.",
                }
    return {
        "source": stored.get("source", "airbyte"),
        "content": redact(
            stored.get(
                "content",
                f"{run['started_at']} INFO Demo sync {run['status']}.\n"
                + (
                    "This run succeeded; no error output was recorded.\n"
                    if run["status"] == "success"
                    else "No failure log was stored for this run.\n"
                ),
            )
        ),
        "redacted": True,
    }


@router.get("/runs/{run_key}", response_model=s.RunDetail)
def run_detail(run_key: str) -> dict:
    return r.detail(run_key)


@router.get("/errors/groups", response_model=s.Page[s.ErrorGroup])
def groups(
    range: str = "7d",
    page: PageNumber = 1,
    page_size: PageSize = 25,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
) -> dict:
    return a.page(a.error_groups(*a.bounds(range, from_, to)), page, page_size)


@router.get("/errors/groups/{fingerprint}", response_model=s.ErrorGroupDetail)
def group(
    fingerprint: str,
    range: str = "7d",
    page: PageNumber = 1,
    page_size: PageSize = 25,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
) -> dict:
    start, end = a.bounds(range, from_, to)
    item = next((g for g in a.error_groups(start, end) if g["fingerprint"] == fingerprint), None)
    if not item:
        fail(404, "group_not_found", "Error group not found in this range.")
    return {
        "group": item,
        "runs": r.list_runs(start, end, fp=fingerprint, page=page, page_size=page_size),
    }


@router.get("/metrics/durations", response_model=s.Page[s.DurationMetric])
def durations(
    range: str = "24h",
    group_by: Literal["pipeline", "tenant"] = "pipeline",
    page: PageNumber = 1,
    page_size: PageSize = 25,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
) -> dict:
    return a.page(a.duration_metrics(*a.bounds(range, from_, to), group_by), page, page_size)


@router.get("/metrics/mttr", response_model=s.Page[s.Mttr])
def mttr(
    range: str = "7d",
    page: PageNumber = 1,
    page_size: PageSize = 25,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
) -> dict:
    items = rows(
        """SELECT m.tenant_id,round(avg(m.recovery_minutes)::numeric,1) AS avg_min,
        count(m.recovered_at) AS recovered,count(*) FILTER(WHERE m.recovered_at IS NULL) AS unresolved
        FROM obs.v_mttr m JOIN obs.pipeline_runs f USING(run_key)
        WHERE f.started_at>=%s AND f.started_at<%s
        GROUP BY m.tenant_id ORDER BY avg_min DESC NULLS LAST""",
        a.bounds(range, from_, to),
    )
    return a.page(items, page, page_size)


@router.get("/metrics/failures-heatmap", response_model=s.Page[s.HeatCell])
def heatmap(
    range: str = "7d",
    tenant: str = "",
    tz: str = "UTC",
    page: PageNumber = 1,
    page_size: PageSize = 200,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
) -> dict:
    start, end = a.bounds(range, from_, to)
    # Buckets are computed in the viewer's timezone so the grid matches the
    # local times shown everywhere else; unknown zones fall back to UTC.
    if not rows("SELECT 1 FROM pg_timezone_names WHERE name=%s", (tz,)):
        tz = "UTC"
    items = rows(
        """SELECT extract(isodow FROM (started_at AT TIME ZONE %s))::integer-1 AS weekday,
                  extract(hour FROM (started_at AT TIME ZONE %s))::integer AS hour,
                  count(*) AS failures
        FROM obs.pipeline_runs WHERE status='failed' AND started_at>=%s AND started_at<%s AND (%s='' OR tenant_id=%s) GROUP BY 1,2 ORDER BY 1,2""",
        (tz, tz, start, end, tenant, tenant),
    )
    return a.page(items, page, page_size)


@router.get("/metrics/failures-breakdown", response_model=s.Page[s.Breakdown])
def failures_breakdown(
    group_by: Literal["stage", "class", "tenant"] = "stage",
    range: str = "24h",
    page: PageNumber = 1,
    page_size: PageSize = 25,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
) -> dict:
    field = {"stage": "r.failed_stage", "class": "e.error_class", "tenant": "r.tenant_id"}[group_by]
    result = rows(
        f"""SELECT coalesce({field},'unknown') AS name,count(*) AS count FROM obs.pipeline_runs r
        LEFT JOIN obs.run_errors e USING(run_key) WHERE r.status='failed' AND started_at>=%s AND started_at<%s
        GROUP BY 1 ORDER BY count DESC""",
        a.bounds(range, from_, to),
    )
    return a.page(result, page, page_size)


@router.get("/freshness", response_model=s.Page[s.Freshness])
def freshness(page: PageNumber = 1, page_size: PageSize = 25) -> dict:
    items = rows(
        "SELECT * FROM obs.v_freshness ORDER BY minutes_stale DESC NULLS FIRST,tenant_id,source_type"
    )
    seven = {(i["tenant_id"], i["source_type"]): i["compliance"] for i in a.sla()}
    thirty = {(i["tenant_id"], i["source_type"]): i["compliance"] for i in a.sla(720)}
    return a.page(
        [
            {
                **i,
                "sla_7d": seven.get((i["tenant_id"], i["source_type"])),
                "sla_30d": thirty.get((i["tenant_id"], i["source_type"])),
            }
            for i in items
        ],
        page,
        page_size,
    )


@router.get("/volume-anomalies", response_model=s.Page[s.Change])
def volume(page: PageNumber = 1, page_size: PageSize = 25) -> dict:
    return a.page(a.anomalies(), page, page_size)


@router.get("/schema-changes", response_model=s.Page[s.Change])
def schema(page: PageNumber = 1, page_size: PageSize = 25) -> dict:
    return a.page(a.schema_changes(), page, page_size)


@router.get("/alerts", response_model=s.Page[s.Alert])
def alerts(
    state: Literal["", "firing", "acked", "resolved"] = "",
    tenant: str = "",
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> dict:
    total = one(
        "SELECT count(*) AS n FROM obs.alerts WHERE (%s='' OR state=%s) AND (%s='' OR tenant_id=%s)",
        (state, state, tenant, tenant),
    )["n"]
    items = rows(
        """SELECT * FROM obs.alerts WHERE (%s='' OR state=%s) AND (%s='' OR tenant_id=%s)
        ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,first_fired_at DESC
        LIMIT %s OFFSET %s""",
        (state, state, tenant, tenant, page_size, (page - 1) * page_size),
    )
    return {"items": redact_tree(items), "total": total, "page": page, "page_size": page_size}


@router.get(
    "/alert-rules",
    response_model=s.Page[s.Rule],
    dependencies=[Depends(require_role("admin", "manage_alerts"))],
)
def rules(page: PageNumber = 1, page_size: PageSize = 25) -> dict:
    return a.page(rows("SELECT * FROM obs.alert_rules ORDER BY rule_id"), page, page_size)


@router.get(
    "/channels",
    response_model=s.Page[s.Channel],
    dependencies=[Depends(require_role("admin", "manage_alerts"))],
)
def channels(page: PageNumber = 1, page_size: PageSize = 25) -> dict:
    return a.page(
        rows("SELECT * FROM obs.notification_channels ORDER BY channel_id"), page, page_size
    )


@router.get(
    "/onboarding/{tenant_id}",
    response_model=s.OnboardProgress,
)
def onboarding(tenant_id: str) -> dict:
    from obs.onboarding.workflow import progress

    return progress(tenant_id)


@router.get("/platform/health", response_model=s.Platform)
def platform() -> dict:
    return a.platform()


@router.get("/search", response_model=s.Page[s.SearchHit])
def search(
    q: str = Query(min_length=2, max_length=200), page: PageNumber = 1, page_size: PageSize = 25
) -> dict:
    where = """ FROM obs.pipeline_runs r LEFT JOIN obs.run_errors e USING(run_key) LEFT JOIN obs.run_logs l USING(run_key)
         WHERE to_tsvector('simple',coalesce(e.error_message,'')) @@ plainto_tsquery('simple',%s)
         OR l.tsv @@ plainto_tsquery('simple',%s)"""
    total = one("SELECT count(*) AS n" + where, (q, q))["n"]
    items = rows(
        "SELECT r.run_key,r.tenant_id,r.started_at,e.error_class,left(coalesce(e.error_message,l.content,''),400) AS excerpt"
        + where
        + " ORDER BY r.started_at DESC LIMIT %s OFFSET %s",
        (q, q, page_size, (page - 1) * page_size),
    )
    return {"items": redact_tree(items), "total": total, "page": page, "page_size": page_size}


@router.get(
    "/audit",
    response_model=s.Page[s.AuditEntry],
    dependencies=[Depends(require_role("admin", "manage_users"))],
)
def audit(page: PageNumber = 1, page_size: PageSize = 25) -> dict:
    total = one("SELECT count(*) AS n FROM obs.audit_log")["n"]
    return {
        "items": redact_tree(
            rows(
                "SELECT * FROM obs.audit_log ORDER BY at DESC LIMIT %s OFFSET %s",
                (page_size, (page - 1) * page_size),
            )
        ),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/users",
    response_model=s.Page[s.User],
    dependencies=[Depends(require_role("admin", "manage_users"))],
)
def users(page: PageNumber = 1, page_size: PageSize = 25) -> dict:
    return a.page(
        rows(
            """SELECT u.user_id,u.email,u.display_name,u.role,u.role_name,
                      (SELECT count(*) FROM obs.sessions ss
                        WHERE ss.user_id=u.user_id AND ss.revoked_at IS NULL
                          AND ss.expires_at>now()) AS active_sessions
               FROM obs.users u ORDER BY u.user_id"""
        ),
        page,
        page_size,
    )


@router.get(
    "/operations",
    response_model=s.Page[s.Operation],
    dependencies=[Depends(require_role("admin", "manage_platform"))],
)
def operations() -> dict:
    items = rows(
        "SELECT id::text,kind,target,actor,status,last_error,created_at,updated_at FROM obs.operations ORDER BY created_at DESC LIMIT 100"
    )
    for item in items:
        item["actor"] = redact(item["actor"])
        item["last_error"] = redact(item["last_error"]) if item["last_error"] else None
    return {"items": items, "total": len(items), "page": 1, "page_size": 100}


@router.get(
    "/deliveries",
    response_model=s.Page[s.Delivery],
    dependencies=[Depends(require_role("admin", "manage_platform"))],
)
def deliveries() -> dict:
    items = rows(
        "SELECT id,channel_id,kind,status,attempts,last_error,at,delivered_at FROM obs.notification_deliveries ORDER BY id DESC LIMIT 100"
    )
    for item in items:
        item["last_error"] = redact(item["last_error"]) if item["last_error"] else None
    return {"items": items, "total": len(items), "page": 1, "page_size": 100}


@router.get("/warehouse", response_model=s.WarehouseView)
def warehouse(tenant: str, user: dict = Depends(current_user)) -> dict:
    if not one("SELECT 1 FROM obs.tenants WHERE tenant_id=%s", (tenant,)):
        fail(404, "tenant_not_found", "Tenant not found.")
    tables = rows(
        """SELECT DISTINCT ON (w.table_name) w.table_name, w.row_count, w.last_loaded_at,
                  (SELECT s.columns FROM obs.schema_snapshots s
                    WHERE s.tenant_id=%s AND s.table_name=w.table_name
                    ORDER BY s.checked_at DESC LIMIT 1) AS columns
           FROM obs.warehouse_snapshots w
           WHERE w.tenant_id=%s
           ORDER BY w.table_name, w.checked_at DESC""",
        (tenant, tenant),
    )
    return {
        "tenant_id": tenant,
        "tables": [
            {
                "table_name": t["table_name"],
                "row_count": t["row_count"],
                "last_loaded_at": t["last_loaded_at"].isoformat() if t["last_loaded_at"] else None,
                "columns": t["columns"] or [],
            }
            for t in tables
        ],
        "table_count": len(tables),
        "total_rows": sum(t["row_count"] or 0 for t in tables),
    }
