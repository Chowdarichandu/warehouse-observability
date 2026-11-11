"""Incidents API: list/detail, acknowledge, resolve with root cause, assign, notes."""

import pytest

from obs.db import connection, one


@pytest.fixture()
def incident_id():
    tenant = one("SELECT tenant_id FROM obs.tenants ORDER BY tenant_id LIMIT 1")["tenant_id"]
    with connection() as conn:
        row = conn.execute(
            """INSERT INTO obs.incidents(tenant_id,source_type,severity,state,title,cause_rule)
               VALUES(%s,'mysql','high','open','Test incident','consecutive_failures')
               RETURNING id""",
            (tenant,),
        ).fetchone()
    incident = str(row["id"])
    yield incident
    with connection() as conn:
        conn.execute("DELETE FROM obs.incident_notes WHERE incident_id=%s", (incident,))
        conn.execute("DELETE FROM obs.incidents WHERE id=%s", (incident,))


def test_incident_list_and_detail(clients, incident_id):
    body = clients["viewer"].get("/api/incidents?state=open").json()
    assert any(item["id"] == incident_id for item in body["items"])
    detail = clients["viewer"].get(f"/api/incidents/{incident_id}").json()
    assert detail["title"] == "Test incident"
    assert detail["alerts"] == [] and detail["notes"] == []


def test_incident_actions_require_operator(clients, incident_id):
    assert clients["viewer"].post(f"/api/incidents/{incident_id}/ack").status_code == 403
    assert clients["viewer"].post(f"/api/incidents/{incident_id}/resolve", json={}).status_code == 403
    assert (
        clients["viewer"]
        .post(f"/api/incidents/{incident_id}/notes", json={"body": "hi"})
        .status_code
        == 403
    )


def test_incident_ack_assign_note_resolve_flow(clients, incident_id):
    ack = clients["operator"].post(f"/api/incidents/{incident_id}/ack")
    assert ack.status_code == 200
    detail = clients["operator"].get(f"/api/incidents/{incident_id}").json()
    assert detail["state"] == "acknowledged"
    assert detail["acknowledged_by"] == "operator@demo.local"

    assign = clients["operator"].post(
        f"/api/incidents/{incident_id}/assign", json={"assignee": "oncall@demo.local"}
    )
    assert assign.status_code == 200
    note = clients["operator"].post(
        f"/api/incidents/{incident_id}/notes", json={"body": "Looking into the binlog gap."}
    )
    assert note.status_code == 200
    detail = clients["operator"].get(f"/api/incidents/{incident_id}").json()
    assert detail["assignee"] == "oncall@demo.local"
    assert [n["body"] for n in detail["notes"]] == ["Looking into the binlog gap."]

    resolve = clients["operator"].post(
        f"/api/incidents/{incident_id}/resolve",
        json={"root_cause_category": "Sync / CDC"},
    )
    assert resolve.status_code == 200
    detail = clients["operator"].get(f"/api/incidents/{incident_id}").json()
    assert detail["state"] == "resolved"
    assert detail["root_cause_category"] == "Sync / CDC"
    # A resolved incident cannot be acknowledged or reassigned.
    assert clients["operator"].post(f"/api/incidents/{incident_id}/ack").status_code == 409
    assert (
        clients["operator"]
        .post(f"/api/incidents/{incident_id}/assign", json={"assignee": "x@demo.local"})
        .status_code
        == 409
    )
