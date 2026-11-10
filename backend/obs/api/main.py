import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from psycopg.types.json import Jsonb
from starlette.exceptions import HTTPException as StarletteHTTPException

from obs.api.routers import (
    access,
    actions,
    auth,
    dependencies,
    investigation,
    pipelines,
    quality,
    read,
    stream,
)
from obs.api.schemas import ErrorEnvelope, RuntimeConfig
from obs.auth import hasher
from obs.db import connection, one
from obs.demo.seed import DEFAULT_RULES
from obs.onboarding.api import router as onboarding_workflow_router
from obs.onboarding.workflow import WorkflowError
from obs.redact import redact
from obs.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings().service_kind != "console":
        raise RuntimeError("The console API requires SERVICE_KIND=console.")
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
    else:
        with connection() as conn:
            for key, name, severity, params in DEFAULT_RULES:
                conn.execute(
                    "INSERT INTO obs.alert_rules(rule_id,name,severity,params) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (key, name, severity, Jsonb(params)),
                )
    yield


app = FastAPI(
    title="Observability Console API",
    version="0.2.0",
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


@app.exception_handler(WorkflowError)
async def workflow_error(request: Request, exc: WorkflowError) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": exc.code, "message": redact(exc.message)}}, status_code=exc.status
    )


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
    started = monotonic()
    supplied = request.headers.get("x-request-id", "")
    request_id = supplied if re.fullmatch(r"[a-zA-Z0-9-]{8,64}", supplied) else str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings().mode == "live":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    logging.info(
        "request method=%s path=%s status=%s duration_ms=%d request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        int((monotonic() - started) * 1000),
        request_id,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health", tags=["Health"])
def health() -> dict:
    one("SELECT 1 AS ok")
    return {"status": "ok", "mode": settings().mode, "version": "0.2.0"}


@app.get("/api/health/live", tags=["Health"])
def liveness() -> dict:
    return {"status": "ok"}


@app.get("/api/config", response_model=RuntimeConfig, tags=["Configuration"])
def runtime_config() -> dict:
    config = settings()
    return {
        "mode": config.mode,
        "environment": "Offline demo" if config.mode == "demo" else config.environment_name,
        "auth_provider": config.auth_provider,
        "live_actions_enabled": config.mode == "demo" or config.live_actions_enabled,
    }


for router in (
    auth.router,
    read.router,
    actions.router,
    stream.router,
    dependencies.router,
    investigation.router,
    quality.router,
    access.router,
    pipelines.router,
    onboarding_workflow_router,
):
    app.include_router(
        router,
        prefix="/api",
        responses={
            code: {"model": ErrorEnvelope} for code in (400, 401, 403, 404, 409, 422, 429, 500)
        },
    )
