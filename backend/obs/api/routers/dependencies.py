from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from obs.auth import current_user, fail
from obs.db import one, rows
from obs.repositories.dependencies import dependency_graph

router = APIRouter(dependencies=[Depends(current_user)], tags=["Dependencies"])


class DependencyTenant(BaseModel):
    tenant_id: str
    display_name: str


class DependencyTenantPage(BaseModel):
    items: list[DependencyTenant]
    total: int
    page: int
    page_size: int


@router.get("/dependencies/tenants", response_model=DependencyTenantPage)
def dependency_tenants(
    q: str = Query("", max_length=200), page: int = Query(1, ge=1, le=1000000)
) -> dict:
    # Avoid calculating health/SLA for every tenant just to populate a picker.
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    predicate = "WHERE display_name ILIKE %s OR tenant_id ILIKE %s"
    total = one("SELECT count(*) AS n FROM obs.tenants " + predicate, (pattern, pattern))["n"]
    items = rows(
        "SELECT tenant_id,display_name FROM obs.tenants "
        + predicate
        + " ORDER BY display_name,tenant_id LIMIT 50 OFFSET %s",
        (pattern, pattern, (page - 1) * 50),
    )
    return {"items": items, "total": total, "page": page, "page_size": 50}


class DependencyNode(BaseModel):
    id: str
    kind: Literal["source", "dag", "task", "connection", "warehouse", "table"]
    label: str
    tenant_id: str
    status: str | None = None
    last_observed_at: datetime | None = None
    evidence: Literal["configured", "observed"]
    run_key: str | None = None


class DependencyEdge(BaseModel):
    id: str
    source: str
    target: str
    relationship: str
    evidence: Literal["configured", "observed"]
    last_observed_at: datetime | None = None


class DependencyGraph(BaseModel):
    tenants: list[DependencyTenant]
    nodes: list[DependencyNode]
    edges: list[DependencyEdge]
    generated_at: datetime
    truncated: bool
    note: str


@router.get("/dependencies", response_model=DependencyGraph)
def dependencies(tenant_id: str = Query("", max_length=200)) -> dict:
    if tenant_id and not one("SELECT 1 FROM obs.tenants WHERE tenant_id=%s", (tenant_id,)):
        fail(404, "tenant_not_found", "Tenant not found.")
    return dependency_graph(tenant_id)
