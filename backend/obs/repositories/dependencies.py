"""An evidence-based dependency map, derived only from stored metadata.

Configured routing and catalog membership are useful dependencies, but are not
proof of record-level or SQL lineage. Keep that distinction on every edge.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from obs.db import rows
from obs.redact import redact_tree

LIMIT = 2000


def _id(kind: str, *parts: str) -> str:
    key = json.dumps(parts, separators=(",", ":"), ensure_ascii=True)
    return f"{kind}:{hashlib.sha256(key.encode()).hexdigest()[:24]}"


def build_graph(tenants: list[dict], runs: list[dict], snapshots: list[dict]) -> dict:
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    ranks: dict[str, Any] = {}

    def node(kind: str, tenant: str, key: str, label: str, **details: Any) -> str:
        key = _id(kind, tenant, key)
        rank = details.pop("_rank", details.get("last_observed_at"))
        value = {
            "id": key,
            "kind": kind,
            "label": label,
            "tenant_id": tenant,
            "status": None,
            "last_observed_at": None,
            "evidence": "configured",
            "run_key": None,
            **details,
        }
        # Runs arrive newest first. Do not replace their health with older rows
        # or an empty configured node when processing the other branches.
        previous = nodes.get(key)
        if previous is None or (rank and (ranks.get(key) is None or rank > ranks[key])):
            nodes[key] = value
            ranks[key] = rank
        return key

    def edge(source: str, target: str, relationship: str, evidence: str, at: Any = None) -> None:
        key = _id("edge", source, target, relationship)
        value = {
            "id": key,
            "source": source,
            "target": target,
            "relationship": relationship,
            "evidence": evidence,
            "last_observed_at": at,
        }
        previous = edges.get(key)
        if previous is None or (
            at and (previous["last_observed_at"] is None or at > previous["last_observed_at"])
        ):
            edges[key] = value

    configs = {t["tenant_id"]: t for t in tenants}
    warehouses: dict[str, str] = {}
    for tenant, config in configs.items():
        if config.get("warehouse_schema"):
            warehouses[tenant] = node(
                "warehouse", tenant, config["warehouse_schema"], config["warehouse_schema"]
            )
        for source in ("mysql", "mongo"):
            if config.get(f"has_{source}"):
                node("source", tenant, source, "MySQL" if source == "mysql" else "MongoDB")
        for pipeline, connection in (config.get("airbyte_connections") or {}).items():
            if not isinstance(connection, str) or not connection:
                continue
            source = (
                "mysql"
                if pipeline.startswith("mysql_")
                else "mongo"
                if pipeline.startswith("mongo_")
                else None
            )
            connection_node = node("connection", tenant, connection, connection)
            if source:
                source_node = node(
                    "source", tenant, source, "MySQL" if source == "mysql" else "MongoDB"
                )
                edge(source_node, connection_node, "Configured source mapping", "configured")
            if tenant in warehouses:
                edge(connection_node, warehouses[tenant], "Tenant destination schema", "configured")

    for run in runs:
        tenant = run["tenant_id"]
        if tenant not in configs:
            continue
        at = run["collected_at"]
        details = {
            "status": run["status"],
            "last_observed_at": at,
            "evidence": "observed",
            "run_key": run["run_key"],
            "_rank": run.get("run_at", at),
        }
        connection_node = None
        if run.get("airbyte_connection_id"):
            connection_node = node(
                "connection",
                tenant,
                run["airbyte_connection_id"],
                run["airbyte_connection_id"],
                **details,
            )
            source_node = node(
                "source",
                tenant,
                run["source_type"],
                "MySQL" if run["source_type"] == "mysql" else "MongoDB",
            )
            edge(source_node, connection_node, "Run source association", "observed", at)
            if tenant in warehouses:
                edge(connection_node, warehouses[tenant], "Tenant destination schema", "configured")
        if run.get("dag_id"):
            dag_node = node(
                "dag",
                tenant,
                run["dag_id"],
                run["dag_id"],
                evidence="observed",
                last_observed_at=at,
                _rank=run.get("run_at", at),
            )
            if run.get("task_id"):
                # Map indexes identify executions; the dependency is the task definition.
                task_node = node(
                    "task", tenant, f"{run['dag_id']}|{run['task_id']}", run["task_id"], **details
                )
                edge(dag_node, task_node, "DAG task membership", "observed", at)
                if connection_node:
                    edge(task_node, connection_node, "Linked pipeline run", "observed", at)

    for snapshot in snapshots:
        tenant = snapshot["tenant_id"]
        if tenant not in warehouses:
            continue
        table_node = node(
            "table",
            tenant,
            snapshot["table_name"],
            snapshot["table_name"],
            evidence="observed",
            last_observed_at=snapshot["checked_at"],
        )
        edge(
            warehouses[tenant],
            table_node,
            "Observed schema membership",
            "observed",
            snapshot["checked_at"],
        )

    return redact_tree(
        {
            "tenants": [
                {"tenant_id": t["tenant_id"], "display_name": t["display_name"]} for t in tenants
            ],
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
            "generated_at": datetime.now(UTC),
            "truncated": False,
            "note": "Configured routes and observed run/catalog relationships. These dependencies do not establish SQL or record-level lineage. Downstream impact shows potentially affected assets, not confirmed failures.",
        }
    )


def dependency_graph(tenant_id: str = "") -> dict:
    tenants = rows(
        """SELECT tenant_id,display_name,has_mysql,has_mongo,airbyte_connections,warehouse_schema
        FROM obs.tenants WHERE (%s='' OR tenant_id=%s) ORDER BY display_name LIMIT 101""",
        (tenant_id, tenant_id),
    )
    selected = [t["tenant_id"] for t in tenants[:100]]
    runs = (
        rows(
            """SELECT DISTINCT ON (tenant_id,dag_id,task_id,airbyte_connection_id)
        tenant_id,source_type,dag_id,task_id,airbyte_connection_id,status,run_key,collected_at,
        coalesce(started_at,queued_at,scheduled_for,collected_at) AS run_at
        FROM obs.pipeline_runs WHERE tenant_id=ANY(%s)
        ORDER BY tenant_id,dag_id,task_id,airbyte_connection_id,
        coalesce(started_at,queued_at,scheduled_for,collected_at) DESC,collected_at DESC,run_key DESC LIMIT %s""",
            (selected, LIMIT + 1),
        )
        if selected
        else []
    )
    snapshots = (
        rows(
            """SELECT DISTINCT ON (tenant_id,table_name) tenant_id,table_name,checked_at
        FROM obs.warehouse_snapshots WHERE tenant_id=ANY(%s)
        ORDER BY tenant_id,table_name,checked_at DESC LIMIT %s""",
            (selected, LIMIT + 1),
        )
        if selected
        else []
    )
    result = build_graph(tenants[:100], runs[:LIMIT], snapshots[:LIMIT])
    result["truncated"] = len(tenants) > 100 or len(runs) > LIMIT or len(snapshots) > LIMIT
    return result
