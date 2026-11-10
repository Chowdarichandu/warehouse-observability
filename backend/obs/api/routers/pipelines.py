"""Read-only seven-DAG catalog; configuration is distinct from execution evidence."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from obs.auth import current_user
from obs.db import rows
from obs.redact import redact_tree
from obs.settings import settings

router = APIRouter(tags=["Pipeline catalog"], dependencies=[Depends(current_user)])

DEFINITIONS = [
    ("coordinator", "Tenant onboarding", None, "Coordinate", []),
    ("mysql_provision", "MySQL provisioning", "mysql", "Provision", ["coordinator"]),
    ("mysql_initial", "MySQL initial load", "mysql", "Initial load", ["mysql_provision"]),
    ("mysql_cdc", "MySQL CDC", "mysql", "Continuous sync", ["mysql_initial"]),
    ("mongo_provision", "MongoDB provisioning", "mongo", "Provision", ["coordinator"]),
    ("mongo_initial", "MongoDB initial load", "mongo", "Initial load", ["mongo_provision"]),
    ("mongo_cdc", "MongoDB CDC", "mongo", "Continuous sync", ["mongo_initial"]),
]


class CatalogDag(BaseModel):
    node_id: str
    label: str
    source: str | None
    phase: str
    dag_id: str
    depends_on: list[str]
    run_policy: str
    latest_status: str | None
    last_recorded_at: datetime | None
    runs_24h: int
    failures_24h: int


class CatalogLaunch(BaseModel):
    tenant_id: str
    display_name: str
    state: str
    updated_at: datetime
    completed: int
    total: int


class PipelineCatalog(BaseModel):
    dags: list[CatalogDag]
    launches: list[CatalogLaunch]
    generated_at: datetime
    simulated: bool
    note: str


@router.get("/pipelines/catalog", response_model=PipelineCatalog)
def catalog() -> dict:
    configured = settings().resolved_onboarding_dags()
    observations = rows(
        """
        WITH recorded AS (
          SELECT dag_id,coalesce(dag_run_id,run_key) AS run_id,status,
            coalesce(started_at,collected_at) AS at
          FROM obs.pipeline_runs WHERE dag_id=ANY(%s)
          UNION ALL
          SELECT dag_id,dag_run_id,status,coalesce(started_at,updated_at)
          FROM obs.onboarding_dag_attempts WHERE dag_id=ANY(%s) AND dag_run_id IS NOT NULL
        ), executions AS (
          SELECT dag_id,run_id,min(at) AS at,
            CASE WHEN bool_or(status='failed') THEN 'failed'
             WHEN bool_or(status='uncertain') THEN 'uncertain'
             WHEN bool_or(status='running') THEN 'running'
             WHEN bool_or(status='queued') THEN 'queued'
             WHEN bool_or(status='success') THEN 'success'
             ELSE min(status) END AS status
          FROM recorded GROUP BY dag_id,run_id
        ) SELECT dag_id,
          (array_agg(status ORDER BY at DESC,run_id))[1] AS latest_status,
          max(at) AS last_recorded_at,
          count(*) FILTER(WHERE at>now()-interval '24 hours') AS runs_24h,
          count(*) FILTER(WHERE status='failed' AND at>now()-interval '24 hours') AS failures_24h
        FROM executions GROUP BY dag_id
    """,
        (list(configured.values()), list(configured.values())),
    )
    evidence = {row["dag_id"]: row for row in observations}
    items = []
    for node, label, source, phase, parents in DEFINITIONS:
        latest = evidence.get(configured[node], {})
        items.append(
            {
                "node_id": node,
                "label": label,
                "source": source,
                "phase": phase,
                "dag_id": configured[node],
                "depends_on": parents,
                "run_policy": "Recurring and onboarding" if node.endswith("_cdc") else "On demand",
                "latest_status": latest.get("latest_status"),
                "last_recorded_at": latest.get("last_recorded_at"),
                "runs_24h": latest.get("runs_24h", 0),
                "failures_24h": latest.get("failures_24h", 0),
            }
        )
    launches = rows("""
        SELECT t.tenant_id,t.display_name,w.state,w.updated_at,
         (SELECT count(*) FROM (SELECT DISTINCT ON(node_id) status FROM obs.onboarding_dag_attempts
          WHERE workflow_id=w.workflow_id ORDER BY node_id,attempt DESC) latest
          WHERE status IN ('success','skipped')) AS completed,
         7 AS total
        FROM obs.onboarding_workflows w JOIN obs.tenants t USING(tenant_id)
        ORDER BY w.updated_at DESC LIMIT 8
    """)
    return redact_tree(
        {
            "dags": items,
            "launches": launches,
            "generated_at": datetime.now(UTC),
            "simulated": settings().mode == "demo",
            "note": "Configured DAG IDs and recorded executions. Configuration alone does not confirm deployment. CDC health outside onboarding is observed through pipeline runs.",
        }
    )
