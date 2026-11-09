from datetime import datetime

from obs.auth import fail
from obs.db import one, rows
from obs.redact import redact_tree


def list_runs(
    start: datetime,
    end: datetime,
    tenant: str = "",
    status: str = "",
    source: str = "",
    load: str = "",
    stage: str = "",
    error_class: str = "",
    q: str = "",
    page: int = 1,
    page_size: int = 25,
    sort: str = "-started_at",
    fp: str = "",
    export: bool = False,
) -> dict:
    clauses = ["r.started_at >= %s", "r.started_at < %s"]
    params: list = [start, end]
    for field, value in [
        ("r.tenant_id", tenant),
        ("r.status", status),
        ("r.source_type", source),
        ("r.load_type", load),
        ("r.failed_stage", stage),
        ("e.error_class", error_class),
        ("e.fingerprint", fp),
    ]:
        if value:
            clauses.append(f"{field}=%s")
            params.append(value)
    if q:
        clauses.append("""(to_tsvector('simple',coalesce(e.error_message,'')) @@ plainto_tsquery('simple',%s)
            OR EXISTS(SELECT 1 FROM obs.run_logs l WHERE l.run_key=r.run_key AND l.tsv @@ plainto_tsquery('simple',%s))
            OR r.tenant_id ILIKE %s OR r.run_key ILIKE %s)""")
        params.extend([q, q, f"%{q}%", f"%{q}%"])
    where = " AND ".join(clauses)
    join = " FROM obs.pipeline_runs r LEFT JOIN obs.run_errors e USING(run_key) WHERE " + where
    total = one("SELECT count(*) AS n" + join, params)["n"]
    field = sort.lstrip("-")
    if field not in {
        "started_at",
        "duration_s",
        "tenant_id",
        "status",
        "rows_synced",
        "queue_delay_s",
    }:
        fail(422, "invalid_sort", "Unsupported sort column.")
    sql = (
        "SELECT r.*,e.error_class"
        + join
        + f" ORDER BY r.{field} {'DESC' if sort.startswith('-') else 'ASC'} NULLS LAST,r.run_key"
    )
    if not export:
        sql += " LIMIT %s OFFSET %s"
        params.extend([page_size, (page - 1) * page_size])
    return {"items": rows(sql, params), "total": total, "page": page, "page_size": page_size}


def detail(key: str) -> dict:
    run = one("SELECT * FROM obs.pipeline_runs WHERE run_key=%s", (key,))
    if not run:
        fail(404, "run_not_found", "Run not found.")
    previous = rows(
        """SELECT * FROM obs.pipeline_runs WHERE tenant_id=%s AND source_type=%s AND load_type=%s
        AND started_at<%s ORDER BY started_at DESC LIMIT 10""",
        (run["tenant_id"], run["source_type"], run["load_type"], run["started_at"]),
    )
    usual = one(
        """SELECT percentile_cont(.5) WITHIN GROUP(ORDER BY duration_s) AS median FROM obs.pipeline_runs
       WHERE tenant_id=%s AND source_type=%s AND load_type=%s AND status='success' AND started_at>now()-interval '7 days'""",
        (run["tenant_id"], run["source_type"], run["load_type"]),
    )
    return {
        "run": run,
        "error": redact_tree(one("SELECT * FROM obs.run_errors WHERE run_key=%s", (key,))) or None,
        "streams": rows(
            "SELECT * FROM obs.run_stream_stats WHERE run_key=%s ORDER BY records DESC", (key,)
        ),
        "previous_runs": previous,
        "usual_duration_s": usual["median"],
    }
