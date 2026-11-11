from datetime import UTC, datetime, timedelta
from time import monotonic

from obs.auth import fail
from obs.db import one, rows
from obs.redact import redact_tree

RANGES = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}
_sla_cache: dict[tuple, tuple[float, list[dict]]] = {}


def bounds(
    range_value: str = "24h", start: datetime | None = None, end: datetime | None = None
) -> tuple[datetime, datetime]:
    end = end or datetime.now(UTC)
    if range_value not in RANGES and not start:
        fail(422, "invalid_range", "Choose 1h, 6h, 24h, 7d, 30d, or supply from/to.")
    start = start or end - timedelta(hours=RANGES.get(range_value, 24))
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or start >= end
        or end - start > timedelta(days=90)
    ):
        fail(422, "invalid_range", "Use UTC offsets, a positive range and at most 90 days.")
    return start, end


def page(items: list[dict], number: int = 1, size: int = 25) -> dict:
    return {
        "items": items[(number - 1) * size : number * size],
        "total": len(items),
        "page": number,
        "page_size": size,
    }


def sla(hours: int = 168, end: datetime | None = None, start: datetime | None = None) -> list[dict]:
    end = end or datetime.now(UTC)
    start = start or end - timedelta(hours=hours)
    key = (start.replace(second=0, microsecond=0), end.replace(second=0, microsecond=0))
    cached = _sla_cache.get(key)
    if cached and monotonic() - cached[0] < 30:
        return cached[1]
    result = rows(
        """WITH sources AS (
        SELECT tenant_id,source_type,freshness_sla_min,registered_at,last_success_at
        FROM obs.v_freshness
      ) SELECT s.tenant_id,s.source_type,
       count(*) AS buckets,
       count(*) FILTER(WHERE obs.metric_is_fresh(b.at,r.last_success_at,s.freshness_sla_min)) AS good_buckets,
       round(100.0*count(*) FILTER(WHERE obs.metric_is_fresh(b.at,r.last_success_at,s.freshness_sla_min))
           /nullif(count(*),0),2) AS compliance
      FROM sources s CROSS JOIN LATERAL generate_series(
          date_bin('5 minutes',greatest(%s::timestamptz,s.registered_at),timestamptz '2000-01-01')
            + CASE WHEN date_bin('5 minutes',greatest(%s::timestamptz,s.registered_at),timestamptz '2000-01-01')
                         < greatest(%s::timestamptz,s.registered_at)
                   THEN interval '5 minutes' ELSE interval '0' END,
          %s::timestamptz-interval '1 microsecond',interval '5 minutes') b(at)
      LEFT JOIN LATERAL(SELECT max(ended_at) AS last_success_at FROM obs.pipeline_runs
        WHERE tenant_id=s.tenant_id AND source_type=s.source_type AND load_type='cdc'
          AND status='success' AND ended_at<=b.at) r ON true
      WHERE b.at>=s.registered_at
        AND NOT EXISTS (
            SELECT 1 FROM obs.maintenance_windows w
            WHERE w.tenant_id=s.tenant_id AND w.rrule IS NULL
              AND b.at>=w.starts_at AND b.at<w.ends_at
        )
      GROUP BY s.tenant_id,s.source_type""",
        (start, start, start, end),
    )
    if len(_sla_cache) > 30:
        _sla_cache.clear()
    _sla_cache[key] = (monotonic(), result)
    return result


def sla_rate(samples: list[dict]) -> float | None:
    buckets = sum(int(sample["buckets"]) for sample in samples)
    return (
        round(100 * sum(int(sample["good_buckets"]) for sample in samples) / buckets, 2)
        if buckets
        else None
    )


def tenants() -> list[dict]:
    compliance = sla()
    result = rows("""SELECT h.*,a.avg_duration_min,a.last_success_at FROM obs.v_tenant_health h
        LEFT JOIN LATERAL(SELECT round((avg(duration_s) FILTER(WHERE status='success')/60)::numeric,2) AS avg_duration_min,
        max(ended_at) FILTER(WHERE status='success' AND load_type='cdc') AS last_success_at
        FROM obs.v_metric_runs WHERE tenant_id=h.tenant_id AND started_at>now()-interval '7 days') a ON true
        ORDER BY CASE h.health WHEN 'down' THEN 0 WHEN 'degraded' THEN 1 WHEN 'onboarding' THEN 2 ELSE 3 END,h.display_name""")
    latest = rows("SELECT * FROM obs.v_latest_runs")
    eligible = {
        r["tenant_id"]
        for r in rows(
            "SELECT DISTINCT tenant_id FROM obs.pipeline_runs WHERE source_type='mysql' AND load_type='initial' AND status='success'"
        )
    }
    for tenant in result:
        tenant["analytics_eligible"] = bool(
            tenant.get("has_mysql", True) and tenant["tenant_id"] in eligible
        )
        tenant["sla_compliance"] = sla_rate(
            [c for c in compliance if c["tenant_id"] == tenant["tenant_id"]]
        )
        tenant["latest_runs"] = [r for r in latest if r["tenant_id"] == tenant["tenant_id"]]
    return result


def duration_metrics(start: datetime, end: datetime, group_by: str = "pipeline") -> list[dict]:
    group = "tenant_id" if group_by == "tenant" else "source_type || ' ' || load_type"
    return rows(
        f"""SELECT {group} AS name,count(*) AS count,
      round((avg(duration_s) FILTER(WHERE status='success')/60)::numeric,2) AS avg_min,
      round((percentile_cont(.5) WITHIN GROUP(ORDER BY duration_s) FILTER(WHERE status='success')/60)::numeric,2) AS p50_min,
      round((percentile_cont(.95) WITHIN GROUP(ORDER BY duration_s) FILTER(WHERE status='success')/60)::numeric,2) AS p95_min,
      round((avg(metric_queue_delay_s)/60)::numeric,2) AS queue_avg_min,
      round((percentile_cont(.95) WITHIN GROUP(ORDER BY metric_queue_delay_s)/60)::numeric,2) AS queue_p95_min
      FROM obs.v_metric_runs WHERE started_at>=%s AND started_at<%s GROUP BY 1 ORDER BY 1""",
        (start, end),
    )


def platform() -> dict:
    return {
        "components": rows(
            "SELECT DISTINCT ON(component) * FROM obs.platform_health ORDER BY component,checked_at DESC"
        ),
        "history": rows("""SELECT DISTINCT ON(component,date_trunc('hour',checked_at),status) * FROM obs.platform_health
                WHERE checked_at>now()-interval '48 hours' ORDER BY component,date_trunc('hour',checked_at),status,checked_at DESC"""),
        "collectors": rows("SELECT * FROM obs.collector_state ORDER BY component"),
        "database_bytes": one("SELECT pg_database_size(current_database()) AS size")["size"],
    }


def overview(start: datetime, end: datetime, include_detail: bool = True) -> dict:
    aggregate = one(
        """SELECT count(*) AS total_runs,count(*) FILTER(WHERE status='failed') AS failed_runs,
      obs.metric_success_rate(count(*) FILTER(WHERE status='success'),count(*) FILTER(WHERE status='failed')) AS success_rate,
      round((avg(duration_s) FILTER(WHERE status='success' AND load_type='cdc')/60)::numeric,2) AS cdc_avg_min,
      round((percentile_cont(.95) WITHIN GROUP(ORDER BY duration_s) FILTER(WHERE status='success' AND load_type='cdc')/60)::numeric,2) AS cdc_p95_min
      FROM obs.v_metric_runs WHERE started_at>=%s AND started_at<%s""",
        (start, end),
    )
    counts = one("""SELECT count(*) FILTER(WHERE health='healthy') AS healthy,count(*) FILTER(WHERE health='degraded') AS degraded,
      count(*) FILTER(WHERE health='down') AS down FROM obs.v_tenant_health""")
    counts.update(
        one("SELECT count(*) AS running_now FROM obs.v_metric_runs WHERE status='running'")
    )
    counts.update(one("SELECT count(*) AS open_alerts FROM obs.alerts WHERE state<>'resolved'"))
    compliance = sla(start=start, end=end)
    aggregate["sla_compliance"] = sla_rate(compliance)
    series = rows(
        """SELECT date_trunc('hour',started_at) AS hour,
      count(*) FILTER(WHERE status='success') AS success,count(*) FILTER(WHERE status='failed') AS failed,
      count(*) FILTER(WHERE status='running') AS running,
      round((avg(duration_s) FILTER(WHERE status='success' AND source_type='mysql' AND load_type='cdc')/60)::numeric,2) AS mysql_cdc,
      round((avg(duration_s) FILTER(WHERE status='success' AND source_type='mongo' AND load_type='cdc')/60)::numeric,2) AS mongo_cdc,
      round((avg(duration_s) FILTER(WHERE status='success' AND source_type='mysql' AND load_type='initial')/60)::numeric,2) AS mysql_initial,
      round((avg(duration_s) FILTER(WHERE status='success' AND source_type='mongo' AND load_type='initial')/60)::numeric,2) AS mongo_initial
      FROM obs.v_metric_runs WHERE started_at>=%s AND started_at<%s GROUP BY 1 ORDER BY 1""",
        (start, end),
    )
    recent = (
        rows(
            """SELECT r.*,e.error_class FROM obs.pipeline_runs r LEFT JOIN obs.run_errors e USING(run_key)
           WHERE r.status='failed' AND started_at>=%s AND started_at<%s ORDER BY started_at DESC LIMIT 6""",
            (start, end),
        )
        if include_detail
        else []
    )
    return {
        "kpis": {**aggregate, **counts},
        "platform": platform()["components"] if include_detail else [],
        "series": series,
        "durations": duration_metrics(start, end),
        "recent_failures": recent,
        "as_of": datetime.now(UTC),
    }


def anomalies() -> list[dict]:
    return rows("""WITH previous AS (
        SELECT *,lag(row_count) OVER w AS previous_count, row_count-lag(row_count) OVER w AS delta,
        lag(checked_at) OVER w AS previous_at FROM obs.warehouse_snapshots
        WINDOW w AS(PARTITION BY tenant_id,table_name ORDER BY checked_at)
      ), baseline AS (
        SELECT *, avg(greatest(delta,0)) OVER(PARTITION BY tenant_id,table_name ORDER BY checked_at
          RANGE BETWEEN interval '7 days' PRECEDING AND interval '1 microsecond' PRECEDING) AS avg_delta FROM previous
      ) SELECT tenant_id,table_name,row_count,previous_count,checked_at,
        round(100.0*(row_count-previous_count)/nullif(previous_count,0),1) AS change_pct
      FROM baseline WHERE checked_at>now()-interval '7 days' AND previous_count>0
      AND (row_count<previous_count*.7 OR(
          row_count>previous_count*1.05 AND delta>5*avg_delta AND avg_delta>0
      ))
      ORDER BY CASE WHEN row_count<previous_count*.7 THEN 0 ELSE 1 END,
          change_pct ASC,checked_at DESC""")


def schema_changes() -> list[dict]:
    changed = rows("""WITH previous AS(SELECT *,lag(columns) OVER w AS previous_columns,lag(columns_hash) OVER w AS previous_hash
       FROM obs.schema_snapshots WINDOW w AS(PARTITION BY tenant_id,table_name ORDER BY checked_at))
       SELECT * FROM previous WHERE previous_hash IS NOT NULL AND columns_hash<>previous_hash ORDER BY checked_at DESC""")
    result = []
    for item in changed:
        before = {c["name"]: c["type"] for c in item["previous_columns"]}
        after = {c["name"]: c["type"] for c in item["columns"]}
        result.append(
            {
                "tenant_id": item["tenant_id"],
                "table_name": item["table_name"],
                "checked_at": item["checked_at"],
                "added": sorted(after.keys() - before.keys()),
                "removed": sorted(before.keys() - after.keys()),
                "type_changed": [
                    f"{key}: {before[key]} → {after[key]}"
                    for key in before.keys() & after.keys()
                    if before[key] != after[key]
                ],
            }
        )
    return result


def error_groups(start: datetime, end: datetime) -> list[dict]:
    groups = rows(
        """SELECT e.fingerprint,e.error_class,min(e.error_message) AS sample_message,count(*) AS occurrences,
        array_agg(DISTINCT e.tenant_id) AS tenants,min(r.started_at) AS first_seen,max(r.started_at) AS last_seen
        FROM obs.run_errors e JOIN obs.pipeline_runs r USING(run_key)
        WHERE r.started_at>=%s AND r.started_at<%s GROUP BY e.fingerprint,e.error_class ORDER BY occurrences DESC""",
        (start, end),
    )
    daily = rows(
        """SELECT e.fingerprint,date_trunc('day',r.started_at) AS day,count(*) AS count
        FROM obs.run_errors e JOIN obs.pipeline_runs r USING(run_key)
        WHERE r.started_at>=%s AND r.started_at<%s GROUP BY 1,2 ORDER BY 2""",
        (start, end),
    )
    for group in groups:
        counts = {
            d["day"].date(): d["count"] for d in daily if d["fingerprint"] == group["fingerprint"]
        }
        group["trend"] = [
            counts.get((start + timedelta(days=i)).date(), 0)
            for i in range((end.date() - start.date()).days + 1)
        ]
    return redact_tree(groups)
