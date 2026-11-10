import json
import time
from collections.abc import AsyncIterator

import psycopg
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from obs.auth import current_user
from obs.settings import settings

router = APIRouter(tags=["Live events"])


@router.get(
    "/stream", responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}}
)
async def stream(request: Request, user: dict = Depends(current_user)) -> EventSourceResponse:
    async def events() -> AsyncIterator[dict[str, str]]:
        async with await psycopg.AsyncConnection.connect(
            settings().database_url, autocommit=True, connect_timeout=5
        ) as conn:
            await conn.execute("LISTEN run_events")
            yield {"event": "stream.ready", "data": json.dumps({"user_id": user["user_id"]})}
            deadline = time.monotonic() + 3600
            while time.monotonic() < deadline and not await request.is_disconnected():
                session = await conn.execute(
                    "SELECT 1 FROM obs.sessions WHERE id=%s AND revoked_at IS NULL AND expires_at>now()",
                    (user["session_id"],),
                )
                if not await session.fetchone():
                    break
                async for event in conn.notifies(timeout=10, stop_after=1):
                    payload = json.loads(event.payload)
                    if "metrics_only" in user["permissions"]:
                        if payload["event"] == "access.changed":
                            yield {"event": "access.changed", "data": "{}"}
                            continue
                        yield {"event": "metrics.refresh", "data": "{}"}
                        continue
                    yield {"event": payload["event"], "data": json.dumps(payload["data"])}

    return EventSourceResponse(
        events(), ping=15, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
