from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from obs.alerter.notify import deliver
from obs.api import schemas as s
from obs.audit import audit
from obs.auth import current_user, fail, require_role
from obs.db import connection, one, rows
from obs.redact import redact_tree

router = APIRouter(dependencies=[Depends(current_user)], tags=["Incidents"])
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]


@router.get("/incidents", response_model=s.Page[s.Incident])
def incidents(
    state: str = "",
    tenant: str = "",
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> dict:
    if state not in {"", "open", "acknowledged", "resolved"}:
        fail(422, "invalid_state", "Use open, acknowledged or resolved.")
    args = (state, state, tenant, tenant)
    total = one(
        """SELECT count(*) AS n FROM obs.incidents
        WHERE (%s='' OR state=%s) AND (%s='' OR tenant_id=%s)""",
        args,
    )["n"]
    items = rows(
        """SELECT * FROM obs.incidents
        WHERE (%s='' OR state=%s) AND (%s='' OR tenant_id=%s)
        ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                 opened_at DESC LIMIT %s OFFSET %s""",
        (*args, page_size, (page - 1) * page_size),
    )
    return {"items": redact_tree(items), "total": total, "page": page, "page_size": page_size}


@router.get("/incidents/{incident_id}", response_model=s.IncidentDetail)
def incident(incident_id: UUID) -> dict:
    item = one("SELECT * FROM obs.incidents WHERE id=%s", (incident_id,))
    if not item:
        fail(404, "incident_not_found", "Incident not found.")
    return {
        **redact_tree(item),
        "alerts": redact_tree(
            rows(
                "SELECT * FROM obs.alerts WHERE incident_id=%s ORDER BY first_fired_at",
                (incident_id,),
            )
        ),
        "notes": redact_tree(
            rows(
                "SELECT * FROM obs.incident_notes WHERE incident_id=%s ORDER BY created_at,id",
                (incident_id,),
            )
        ),
    }


@router.post("/incidents/{incident_id}/ack", response_model=s.Message)
def acknowledge(
    incident_id: UUID, user: dict = Depends(require_role("operator", "manage_alerts"))
) -> dict:
    with connection() as conn:
        item = conn.execute(
            "SELECT * FROM obs.incidents WHERE id=%s FOR UPDATE", (incident_id,)
        ).fetchone()
        if not item:
            fail(404, "incident_not_found", "Incident not found.")
        if item["state"] == "resolved":
            fail(409, "incident_resolved", "A resolved incident cannot be acknowledged.")
        conn.execute(
            "UPDATE obs.incidents SET state='acknowledged',acknowledged_by=%s,acknowledged_at=now(),updated_at=now() WHERE id=%s",
            (user["email"], incident_id),
        )
        conn.execute(
            "UPDATE obs.alerts SET state='acked',acked_by=%s,acked_at=now() WHERE incident_id=%s AND state='firing'",
            (user["email"], incident_id),
        )
        audit(conn, user["email"], "ack_incident", str(incident_id))
    return {"message": "Incident acknowledged. Repeat notifications are muted."}


@router.post("/incidents/{incident_id}/resolve", response_model=s.Message)
def resolve(
    incident_id: UUID, user: dict = Depends(require_role("operator", "manage_alerts"))
) -> dict:
    with connection() as conn:
        item = conn.execute(
            "SELECT * FROM obs.incidents WHERE id=%s FOR UPDATE", (incident_id,)
        ).fetchone()
        if not item:
            fail(404, "incident_not_found", "Incident not found.")
        if item["state"] == "resolved":
            return {"message": "Incident is already resolved."}
        alerts = conn.execute(
            "SELECT * FROM obs.alerts WHERE incident_id=%s AND state<>'resolved' FOR UPDATE",
            (incident_id,),
        ).fetchall()
        conn.execute(
            "UPDATE obs.incidents SET state='resolved',resolved_by=%s,resolved_at=now(),updated_at=now() WHERE id=%s",
            (user["email"], incident_id),
        )
        for alert in alerts:
            conn.execute(
                "UPDATE obs.alerts SET state='resolved',resolved_by=%s,resolved_at=now() WHERE id=%s",
                (user["email"], alert["id"]),
            )
            rule = conn.execute(
                "SELECT channels FROM obs.alert_rules WHERE rule_id=%s", (alert["rule_id"],)
            ).fetchone()
            for channel in rule["channels"] if rule else []:
                deliver(conn, channel, "resolved", alert["title"], alert["id"])
        audit(conn, user["email"], "resolve_incident", str(incident_id))
    return {"message": "Incident resolved."}


@router.post("/incidents/{incident_id}/notes", response_model=s.IncidentNote)
def note(
    incident_id: UUID,
    data: s.IncidentNoteInput,
    user: dict = Depends(require_role("operator", "manage_alerts")),
) -> dict:
    with connection() as conn:
        if not conn.execute("SELECT 1 FROM obs.incidents WHERE id=%s", (incident_id,)).fetchone():
            fail(404, "incident_not_found", "Incident not found.")
        item = conn.execute(
            "INSERT INTO obs.incident_notes(incident_id,author,body) VALUES(%s,%s,%s) RETURNING *",
            (incident_id, user["email"], data.body.strip()),
        ).fetchone()
        audit(conn, user["email"], "add_incident_note", str(incident_id))
    return item
