import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from obs.audit import audit
from obs.auth import fail
from obs.db import connection, notify, rows
from obs.integrations import warehouse
from obs.quality.models import QualityCheckInput, identifier
from obs.redact import redact_tree
from obs.settings import settings


def assess(check: dict, samples: list[dict], columns: dict[str, str]) -> tuple[str, dict]:
    """Only aggregate evidence leaves this function; sample values are never persisted."""
    kind, params = check["kind"], check["params"]
    if kind == "schema_contract":
        expected = params["columns"]
        missing = sorted(set(expected) - set(columns))
        changed = sorted(
            name for name in set(expected) & set(columns) if expected[name] != columns[name].lower()
        )
        extra = sorted(set(columns) - set(expected)) if not params["allow_extra"] else []
        return ("fail" if missing or changed or extra else "pass"), {
            "missing_columns": missing,
            "type_mismatches": changed,
            "unexpected_columns": extra,
            "scope": "catalog schema contract",
        }
    if kind == "tenant_isolation":
        if check["params"]["tenant_field"] not in columns:
            return "error", {
                "message": "The configured tenant field is absent from the table catalog."
            }
        if not samples:
            return "error", {
                "message": "No aggregate result; tenant isolation cannot be established."
            }
        evidence = samples[0]
        foreign_rows = int(evidence.get("foreign_rows") or 0)
        total_rows = int(evidence.get("total_rows") or 0)
        return ("fail" if foreign_rows else "pass"), {
            "foreign_rows": foreign_rows,
            "total_rows": total_rows,
            "scope": "full-table tenant field aggregate",
        }
    required = params.get("columns", [params.get("column")])
    if any(name not in columns for name in required):
        return "error", {"message": "A configured column is absent from the table catalog."}
    if not samples:
        return "error", {"message": "No rows sampled; data quality cannot be established."}
    total = len(samples)
    if kind == "null_rate":
        failures = sum(row[params["column"]] is None for row in samples)
        threshold = params["max_null_rate"]
    elif kind == "duplicate_keys":
        keys = Counter(
            tuple(str(row[name]) if row[name] is not None else None for name in required)
            for row in samples
        )
        failures = sum(count - 1 for count in keys.values())
        threshold = params["max_duplicate_rate"]
    else:
        allowed = set(params["values"])
        failures = sum(
            row[params["column"]] is None or str(row[params["column"]]) not in allowed
            for row in samples
        )
        threshold = params["max_invalid_rate"]
    rate = failures / total
    return ("pass" if rate <= threshold else "fail"), {
        "violations": failures,
        "violation_rate": round(rate, 6),
        "maximum_rate": threshold,
        "scope": "bounded sample; not a full-table guarantee",
    }


def sample_query(schema: str, table: str, columns: list[str]) -> sql.Composed:
    return sql.SQL("SELECT {} FROM {}.{} LIMIT %s").format(
        sql.SQL(",").join(sql.Identifier(identifier(name)) for name in columns),
        sql.Identifier(identifier(schema)),
        sql.Identifier(identifier(table)),
    )


def live_evidence(check: dict, schema: str) -> tuple[list[dict], dict[str, str]]:
    with warehouse.connect() as source:
        source.execute("SET TRANSACTION READ ONLY")
        # Keep even a misconfigured warehouse timeout bounded for interactive checks.
        timeout = min(settings().warehouse_statement_timeout_ms, 10000)
        source.execute(sql.SQL("SET LOCAL statement_timeout TO {}").format(sql.Literal(timeout)))
        columns = {
            row["column_name"]: row["data_type"]
            for row in source.execute(
                "SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position LIMIT 1001",
                (schema, check["table_name"]),
            ).fetchall()
        }
        if len(columns) > 1000:
            raise ValueError("Catalog exceeds the supported 1000-column bound")
        if not columns:
            raise ValueError("Table is not visible in the registered warehouse schema")
        if check["kind"] == "schema_contract":
            return [], columns
        if check["kind"] == "tenant_isolation":
            tenant_field = identifier(check["params"]["tenant_field"])
            aggregate = source.execute(
                sql.SQL(
                    "SELECT COUNT(*) FILTER (WHERE {} IS DISTINCT FROM %s) AS foreign_rows, COUNT(*) AS total_rows FROM {}.{}"
                ).format(
                    sql.Identifier(tenant_field),
                    sql.Identifier(identifier(schema)),
                    sql.Identifier(identifier(check["table_name"])),
                ),
                (check["tenant_id"],),
            ).fetchone()
            return [dict(aggregate)], columns
        selected = check["params"].get("columns", [check["params"].get("column")])
        if any(name not in columns for name in selected):
            return [], columns
        samples = source.execute(
            sample_query(schema, check["table_name"], selected), (check["sample_limit"],)
        ).fetchall()
        return samples, columns


def demo_evidence(conn: psycopg.Connection, check: dict) -> tuple[list[dict], dict[str, str]]:
    if check["kind"] == "tenant_isolation":
        # The demo models shared Mongo collections partitioned by the tenant
        # field, so isolation evidence does not depend on the table catalog:
        # no foreign rows are ever simulated outside the scripted history.
        field = str(check["params"].get("tenant_field") or "tenant_id")
        return [{"foreign_rows": 0, "total_rows": 100}], {field: "text"}
    snapshot = conn.execute(
        "SELECT columns FROM obs.schema_snapshots WHERE tenant_id=%s AND table_name=%s ORDER BY checked_at DESC LIMIT 1",
        (check["tenant_id"], check["table_name"]),
    ).fetchone()
    columns = {item["name"]: item["type"] for item in snapshot["columns"]} if snapshot else {}
    if not columns:
        raise ValueError("No demo catalog for this table")
    samples = []
    for index in range(min(100, check["sample_limit"])):
        row: dict[str, Any] = {name: index for name in columns}
        row["id"] = index if check["tenant_id"] != "cedar_foods" or index != 99 else 0
        row["amount"] = None if check["tenant_id"] == "acme_retail" and index < 8 else index * 10
        row["updated_at"] = datetime.now(UTC)
        samples.append(row)
    return samples, columns


def execute(conn: psycopg.Connection, check: dict) -> dict:
    # Revalidate persisted definitions, including scheduler execution, before constructing SQL.
    definition = (
        QualityCheckInput.model_validate(check).model_dump()
        if "id" not in check
        else QualityCheckInput.model_validate(
            {k: check[k] for k in QualityCheckInput.model_fields}
        ).model_dump()
    )
    check = {**check, **definition}
    tenant = conn.execute(
        "SELECT * FROM obs.tenants WHERE tenant_id=%s", (check["tenant_id"],)
    ).fetchone()
    if not tenant or tenant["status"] != "active":
        fail(409, "tenant_inactive", "Checks require an active registered tenant.")
    try:
        if settings().mode == "demo":
            samples, columns = demo_evidence(conn, check)
        else:
            schema = tenant.get("warehouse_schema")
            if not schema:
                raise ValueError("Tenant warehouse schema is not configured")
            samples, columns = live_evidence(check, identifier(schema))
        status, details = assess(check, samples, columns)
        sampled = (
            int(details.get("total_rows", 0))
            if check["kind"] == "tenant_isolation"
            else len(samples)
            if check["kind"] != "schema_contract"
            else 0
        )
    except Exception as exc:
        # Driver exceptions can contain sampled row values or credentials: persist only class.
        status, sampled = "error", 0
        details = {
            "message": f"Quality evidence unavailable ({type(exc).__name__}). Check warehouse access, catalog columns and timeout."
        }
    result = conn.execute(
        """INSERT INTO obs.quality_results(check_id,tenant_id,status,sampled_rows,details,simulated)
        VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            check["id"],
            check["tenant_id"],
            status,
            sampled,
            Jsonb(redact_tree(details)),
            settings().mode == "demo",
        ),
    ).fetchone()
    conn.execute("UPDATE obs.quality_checks SET last_checked_at=now() WHERE id=%s", (check["id"],))
    if check["kind"] == "tenant_isolation" and status in {"fail", "error"}:
        # Isolation failures are security incidents, even when the quality
        # worker cannot associate them with a pipeline run key.
        title = "Tenant isolation check failed"
        incident = conn.execute(
            """INSERT INTO obs.incidents(tenant_id,source_type,severity,title,cause_rule)
               SELECT %s, 'mongo',
                      'critical', %s, 'tenant_isolation'
                FROM obs.tenants t
               WHERE t.tenant_id=%s AND t.sources->'mongo'->>'shared'='true'
                 AND NOT EXISTS (
                  SELECT 1 FROM obs.incidents
                   WHERE tenant_id=%s AND cause_rule='tenant_isolation'
                     AND state IN ('open','acknowledged'))""",
            (check["tenant_id"], title, check["tenant_id"], check["tenant_id"]),
        )
        if incident.rowcount:
            notify(
                conn,
                "incident.created",
                {
                    "tenant_id": check["tenant_id"],
                    "severity": "critical",
                    "rule_id": "tenant_isolation",
                },
            )
    if (
        check["kind"] == "tenant_isolation"
        and status == "fail"
        and int(details.get("foreign_rows", 0)) > 0
        and settings().mode == "live"
        and settings().live_actions_enabled
    ):
        tenant = conn.execute(
            "SELECT tenant_id,sources,status FROM obs.tenants WHERE tenant_id=%s FOR UPDATE",
            (check["tenant_id"],),
        ).fetchone()
        mongo = (tenant or {}).get("sources", {}).get("mongo", {})
        if tenant and mongo.get("shared") and tenant["status"] == "active":
            conn.execute(
                "UPDATE obs.tenants SET status='paused',updated_at=now() WHERE tenant_id=%s",
                (check["tenant_id"],),
            )
            audit(
                conn,
                "quality:worker",
                "tenant_paused_isolation_breach",
                check["tenant_id"],
                {"check_id": check["id"], "foreign_rows": int(details["foreign_rows"])},
            )
            notify(
                conn,
                "tenant.paused",
                {"tenant_id": check["tenant_id"], "reason": "tenant_isolation"},
            )
    notify(conn, "quality.updated", {"tenant_id": check["tenant_id"], "status": status})
    return result


def evaluate_due() -> None:
    if settings().mode == "live" and not settings().quality_enabled:
        return
    candidates = rows(
        """SELECT q.id FROM obs.quality_checks q JOIN obs.tenants t USING(tenant_id)
        WHERE q.enabled AND t.status='active' AND
        (q.last_checked_at IS NULL OR q.last_checked_at<now()-q.interval_sec*interval '1 second')
        ORDER BY q.last_checked_at NULLS FIRST LIMIT 25"""
    )
    for item in candidates:
        try:
            with connection() as conn:
                check = conn.execute(
                    """SELECT * FROM obs.quality_checks WHERE id=%s AND enabled AND
                    (last_checked_at IS NULL OR last_checked_at<now()-interval_sec*interval '1 second')
                    FOR UPDATE SKIP LOCKED""",
                    (item["id"],),
                ).fetchone()
                if check:
                    execute(conn, check)
        except Exception as exc:
            # Record configuration/registry failures without including driver text or row values.
            message = f"Quality scheduler failure ({type(exc).__name__}); review the check definition and tenant registry."
            logging.error("quality:%s: %s", item["id"], message)
            with connection() as conn:
                conn.execute(
                    """INSERT INTO obs.collector_state(component,last_error) VALUES(%s,%s)
                    ON CONFLICT(component) DO UPDATE SET last_error=excluded.last_error,updated_at=now()""",
                    (f"quality:{item['id']}", message),
                )
    with connection() as conn:
        conn.execute(
            "DELETE FROM obs.quality_results WHERE id IN (SELECT id FROM obs.quality_results WHERE checked_at<now()-interval '90 days' LIMIT 10000)"
        )
