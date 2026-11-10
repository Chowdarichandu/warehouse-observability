"""Read-only DAG catalog: the seven onboarding DAGs plus the analytics DAGs,
with execution evidence from recorded pipeline runs and tenant events.
Configuration is distinct from execution evidence."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from obs.auth import current_user
from obs.db import rows
from obs.onboarding.service import plan_for
from obs.redact import redact_tree
from obs.settings import settings

router = APIRouter(tags=["Pipeline catalog"], dependencies=[Depends(current_user)])

# node_id, label, source, phase, dag_id, depends_on, run_policy, evidence
# evidence is ("run", source, load) for pipeline-run-backed DAGs or
# ("events", [step names]) / ("analytics", dag_id) for event-backed DAGs.
DEFINITIONS = [
    (
        "coordinator",
        "Tenant onboarding",
        None,
        "Coordinate",
        "tenant_onboarding",
        [],
        "On demand",
        (
            "events",
            [
                "Validate onboarding request",
                "Create tenant record",
                "Create warehouse schema",
                "Create Airbyte connections",
            ],
        ),
    ),
    (
        "mysql_provision",
        "MySQL provisioning",
        "mysql",
        "Provision",
        "mysql_provisioning",
        ["coordinator"],
        "On demand",
        ("events", ["Create dedicated MySQL database", "Provision MySQL user and grants"]),
    ),
    (
        "mysql_initial",
        "MySQL initial load",
        "mysql",
        "Initial load",
        "mysql_initial_load",
        ["mysql_provision"],
        "On demand",
        ("run", "mysql", "initial"),
    ),
    (
        "mysql_cdc",
        "MySQL CDC",
        "mysql",
        "Continuous sync",
        "mysql_cdc",
        ["mysql_initial"],
        "Recurring and onboarding",
        ("run", "mysql", "cdc"),
    ),
    (
        "mongo_provision",
        "MongoDB provisioning",
        "mongo",
        "Provision",
        "mongodb_provisioning",
        ["coordinator"],
        "On demand",
        ("events", ["Register shared MongoDB cluster", "Configure tenant document key"]),
    ),
    (
        "mongo_initial",
        "MongoDB initial load",
        "mongo",
        "Initial load",
        "mongodb_initial_load",
        ["mongo_provision"],
        "On demand",
        ("run", "mongo", "initial"),
    ),
    (
        "mongo_cdc",
        "MongoDB CDC",
        "mongo",
        "Continuous sync",
        "mongodb_cdc",
        ["mongo_initial"],
        "Recurring and onboarding",
        ("run", "mongo", "cdc"),
    ),
    (
        "analytics_marts",
        "Analytics marts build",
        None,
        "Analytics",
        "analytics_marts",
        ["mysql_initial"],
        "On demand",
        ("analytics", "analytics_marts"),
    ),
    (
        "analytics_rollup",
        "KPI rollup",
        None,
        "Analytics",
        "analytics_rollup",
        ["analytics_marts"],
        "On demand",
        ("analytics", "analytics_rollup"),
    ),
    (
        "analytics_quality",
        "Analytics quality checks",
        None,
        "Analytics",
        "analytics_quality",
        ["mysql_initial"],
        "On demand",
        ("analytics", "analytics_quality"),
    ),
]

EVENT_STATUS = {"ok": "success", "started": "running", "failed": "failed"}


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


def _run_evidence(source: str, load: str) -> dict:
    found = rows(
        """SELECT
             (SELECT status FROM obs.pipeline_runs
              WHERE source_type=%s AND load_type=%s
              ORDER BY started_at DESC NULLS LAST LIMIT 1) AS latest_status,
             max(started_at) AS last_recorded_at,
             count(*) FILTER (WHERE started_at>now()-interval '24 hours') AS runs_24h,
             count(*) FILTER (WHERE status='failed' AND started_at>now()-interval '24 hours') AS failures_24h
           FROM obs.pipeline_runs WHERE source_type=%s AND load_type=%s""",
        (source, load, source, load),
    )
    return found[0] if found else {}


def _event_evidence(steps: list) -> dict:
    found = rows(
        """SELECT status, at FROM obs.tenant_events
           WHERE step = ANY(%s) ORDER BY at DESC""",
        (steps,),
    )
    if not found:
        return {}
    recent = [e for e in found if (datetime.now(UTC) - e["at"]).days < 1]
    return {
        "latest_status": EVENT_STATUS.get(found[0]["status"], found[0]["status"]),
        "last_recorded_at": found[0]["at"],
        "runs_24h": sum(1 for e in recent if e["status"] == "started"),
        "failures_24h": sum(1 for e in recent if e["status"] == "failed"),
    }


def _analytics_evidence(dag_id: str) -> dict:
    return _event_evidence([f"analytics:{dag_id}"])


@router.get("/pipelines/catalog", response_model=PipelineCatalog)
def catalog() -> dict:
    items = []
    for node, label, source, phase, dag_id, parents, policy, evidence in DEFINITIONS:
        kind = evidence[0]
        if kind == "run":
            found = _run_evidence(evidence[1], evidence[2])
        elif kind == "analytics":
            found = _analytics_evidence(evidence[1])
        else:
            found = _event_evidence(evidence[1])
        items.append(
            {
                "node_id": node,
                "label": label,
                "source": source,
                "phase": phase,
                "dag_id": dag_id,
                "depends_on": parents,
                "run_policy": policy,
                "latest_status": found.get("latest_status"),
                "last_recorded_at": found.get("last_recorded_at"),
                "runs_24h": found.get("runs_24h", 0),
                "failures_24h": found.get("failures_24h", 0),
            }
        )
    launches = []
    jobs = rows(
        """SELECT j.tenant_id, j.step, j.done, j.due_at, t.display_name,
                  t.has_mysql, t.has_mongo
           FROM obs.demo_jobs j JOIN obs.tenants t USING (tenant_id)
           WHERE j.kind='onboarding' ORDER BY j.due_at DESC LIMIT 8"""
    )
    for job in jobs:
        total = len(plan_for(job))
        launches.append(
            {
                "tenant_id": job["tenant_id"],
                "display_name": job["display_name"],
                "state": "completed" if job["done"] else "running",
                "updated_at": job["due_at"],
                "completed": min(job["step"], total),
                "total": total,
            }
        )
    return redact_tree(
        {
            "dags": items,
            "launches": launches,
            "generated_at": datetime.now(UTC),
            "simulated": settings().mode == "demo",
            "note": "Configured DAG IDs with recorded executions. CDC health outside onboarding is observed through pipeline runs; analytics DAGs run from a tenant's Workflows panel once its MySQL initial load has passed.",
        }
    )
