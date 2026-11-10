from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from obs.api.main import app
from obs.repositories.dependencies import build_graph

NOW = datetime.now(UTC)
TENANT = {
    "tenant_id": "unit_tenant",
    "display_name": "Unit Tenant",
    "has_mysql": True,
    "has_mongo": False,
    "warehouse_schema": "unit_warehouse",
    "airbyte_connections": {"mysql_cdc": "unit-connection"},
}


def run(**overrides: object) -> dict:
    return {
        "tenant_id": "unit_tenant",
        "source_type": "mysql",
        "dag_id": "shared_cdc",
        "task_id": "sync_tenant",
        "airbyte_connection_id": "unit-connection",
        "status": "failed",
        "run_key": "run-unit-tenant-1",
        "collected_at": NOW,
        **overrides,
    }


def test_graph_distinguishes_configuration_from_execution_and_catalog() -> None:
    graph = build_graph(
        [TENANT],
        [run()],
        [{"tenant_id": "unit_tenant", "table_name": "orders", "checked_at": NOW}],
    )
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert {node["kind"] for node in nodes.values()} == {
        "source",
        "dag",
        "task",
        "connection",
        "warehouse",
        "table",
    }
    assert all(
        edge["source"] in nodes and edge["target"] in nodes for edge in graph["edges"]
    )
    assert {edge["evidence"] for edge in graph["edges"]} == {"configured", "observed"}
    assert any(
        edge["relationship"] == "Linked pipeline run" and edge["evidence"] == "observed"
        for edge in graph["edges"]
    )
    assert any(
        edge["relationship"] == "Tenant destination schema"
        and edge["evidence"] == "configured"
        for edge in graph["edges"]
    )
    assert "do not establish SQL" in graph["note"]
    connection = next(node for node in nodes.values() if node["kind"] == "connection")
    assert connection["status"] == "failed"
    assert connection["run_key"] == "run-unit-tenant-1"


def test_shared_dag_and_connection_do_not_cross_tenant_boundaries() -> None:
    other = {**TENANT, "tenant_id": "other_tenant", "display_name": "Other"}
    graph = build_graph([TENANT, other], [run(), run(tenant_id="other_tenant")], [])
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert len({node["id"] for node in nodes.values() if node["kind"] == "dag"}) == 2
    assert all(
        nodes[edge["source"]]["tenant_id"] == nodes[edge["target"]]["tenant_id"]
        for edge in graph["edges"]
    )


def test_latest_observation_wins_and_missing_link_is_not_invented() -> None:
    graph = build_graph(
        [TENANT],
        [
            run(),
            run(status="success", collected_at=NOW - timedelta(hours=1)),
            run(dag_id=None, task_id=None, airbyte_connection_id=None),
        ],
        [],
    )
    connection = next(node for node in graph["nodes"] if node["kind"] == "connection")
    assert connection["status"] == "failed"
    assert len([node for node in graph["nodes"] if node["kind"] == "task"]) == 1
    empty = build_graph([{**TENANT, "airbyte_connections": {}}], [], [])
    assert empty["edges"] == []


def test_recollecting_old_run_does_not_replace_latest_execution_status() -> None:
    graph = build_graph(
        [TENANT],
        [
            run(status="success", run_at=NOW - timedelta(days=1), collected_at=NOW),
            run(
                status="failed",
                run_at=NOW - timedelta(hours=1),
                collected_at=NOW - timedelta(minutes=1),
            ),
        ],
        [],
    )
    connection = next(node for node in graph["nodes"] if node["kind"] == "connection")
    assert connection["status"] == "failed"
    assert connection["last_observed_at"] == NOW - timedelta(minutes=1)


def test_graph_read_requires_authentication() -> None:
    with TestClient(app, base_url="https://localhost") as client:
        assert client.get("/api/dependencies").status_code == 401


def test_viewer_can_inspect_seeded_graph_and_unknown_tenant_returns_404(
    clients: dict,
) -> None:
    response = clients["viewer"].get("/api/dependencies?tenant_id=acme_retail")
    assert response.status_code == 200, response.text
    graph = response.json()
    assert graph["nodes"] and graph["edges"]
    assert all(node["tenant_id"] == "acme_retail" for node in graph["nodes"])
    assert not graph["truncated"]
    assert (
        clients["viewer"]
        .get("/api/dependencies?tenant_id=no_such_dependency_tenant")
        .status_code
        == 404
    )


def test_tenant_picker_search_is_literal_paginated_and_authenticated(
    clients: dict,
) -> None:
    viewer = clients["viewer"]
    response = viewer.get("/api/dependencies/tenants", params={"q": "acme_retail"})
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {"tenant_id": "acme_retail", "display_name": "Acme Retail"}
    ]
    assert response.json()["page_size"] == 50
    assert (
        viewer.get("/api/dependencies/tenants", params={"q": "%"}).json()["items"] == []
    )
    assert viewer.get("/api/dependencies/tenants?page=0").status_code == 422
    assert viewer.get("/api/dependencies/tenants?page=1000001").status_code == 422
    with TestClient(app, base_url="https://localhost") as client:
        assert client.get("/api/dependencies/tenants").status_code == 401
