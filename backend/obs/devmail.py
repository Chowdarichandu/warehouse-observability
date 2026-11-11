"""Dev mailbox capture (SPEC §13).

In demo mode there is no mail server: account emails are recorded in
obs.dev_mailbox so an admin can read them at /dev/mailbox. In live mode
this is a no-op; real delivery belongs to the identity provider.
"""

import psycopg

from obs.settings import settings


def record_email(conn: psycopg.Connection, recipient: str, subject: str, body: str) -> None:
    if settings().mode != "demo":
        return
    conn.execute(
        "INSERT INTO obs.dev_mailbox(recipient,subject,body) VALUES(%s,%s,%s)",
        (recipient, subject, body),
    )
