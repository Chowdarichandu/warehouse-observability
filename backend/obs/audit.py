import psycopg
from psycopg.types.json import Jsonb

from obs.redact import redact_tree


def audit(
    conn: psycopg.Connection,
    actor: str,
    action: str,
    target: str | None = None,
    details: dict | None = None,
) -> None:
    conn.execute(
        "INSERT INTO obs.audit_log(actor,action,target,details) VALUES(%s,%s,%s,%s)",
        (actor, action, target, Jsonb(redact_tree(details or {}))),
    )
