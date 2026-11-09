import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from psycopg.types.json import Jsonb
from starlette.exceptions import HTTPException as StarletteHTTPException

from obs.api.routers import actions, auth, read, stream
from obs.api.schemas import ErrorEnvelope
from obs.auth import hasher
from obs.db import connection, one
from obs.demo.seed import DEFAULT_RULES
from obs.redact import redact
from obs.settings import require_demo, settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    require_demo()
    if settings().mode == "demo":
        with connection() as conn:
            for role in ("admin", "operator", "viewer"):
                if not conn.execute(
                    "SELECT 1 FROM obs.users WHERE email=%s", (f"{role}@demo.local",)
                ).fetchone():
                    conn.execute(
                        "INSERT INTO obs.users(email,display_name,role,password_hash) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (
                            f"{role}@demo.local",
                            f"Demo {role.title()}",
                            role,
                            hasher.hash(settings().demo_password),
                        ),
                    )
            for key, name, severity, params in DEFAULT_RULES:
                conn.execute(
                    "INSERT INTO obs.alert_rules(rule_id,name,severity,params,channels) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (key, name, severity, Jsonb(params), ["slack-data-eng"]),
                )
            for channel, kind, env in [
                ("slack-data-eng", "slack", "SLACK_WEBHOOK_URL"),
                ("teams-operations", "teams", "TEAMS_WEBHOOK_URL"),
                ("email-oncall", "email", "SMTP_URL"),
            ]:
                conn.execute(
                    "INSERT INTO obs.notification_channels(channel_id,kind,target_env) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                    (channel, kind, env),
                )
    yield


app = FastAPI(
    title="Observability Console API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    detail = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {"code": f"http_{exc.status_code}", "message": str(exc.detail)}
    )
    return JSONResponse({"error": detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors())
    return JSONResponse(
        {"error": {"code": "validation_error", "message": f"Invalid input: {fields}"}},
        status_code=422,
    )


@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    logging.error("API exception: %s", redact(str(exc)))
    return JSONResponse(
        {
            "error": {
                "code": "internal_error",
                "message": "The request could not be completed. Check service health and retry.",
            }
        },
        status_code=500,
    )


@app.middleware("http")
async def headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health", tags=["Health"])
def health() -> dict:
    one("SELECT 1 AS ok")
    return {"status": "ok", "mode": settings().mode, "milestone": "M4"}


for router in (auth.router, read.router, actions.router, stream.router):
    app.include_router(
        router,
        prefix="/api",
        responses={
            code: {"model": ErrorEnvelope} for code in (400, 401, 403, 404, 409, 422, 429, 500)
        },
    )
