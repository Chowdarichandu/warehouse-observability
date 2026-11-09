import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from obs.settings import settings


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(
        settings().database_url,
        row_factory=dict_row,
        connect_timeout=5,
        application_name="obs-console",
        options="-c statement_timeout=30000 -c idle_in_transaction_session_timeout=60000",
    ) as conn:
        conn.execute("SET TIME ZONE 'UTC'")
        yield conn


def rows(sql: str, params: Any = None) -> list[dict]:
    with connection() as conn:
        return conn.execute(sql, params).fetchall()


def one(sql: str, params: Any = None) -> dict:
    with connection() as conn:
        return conn.execute(sql, params).fetchone() or {}


def notify(conn: psycopg.Connection, event: str, payload: dict) -> None:
    message = json.dumps({"event": event, "data": payload}, default=str)
    if len(message.encode()) >= 8000:
        raise ValueError("Event exceeds PostgreSQL NOTIFY limit")
    conn.execute("SELECT pg_notify('run_events', %s)", (message,))
