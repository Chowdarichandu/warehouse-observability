"""Durable onboarding worker, invoked inside the reviewed onboard_tenant DAG."""

import time
from collections.abc import Callable

from psycopg.types.json import Jsonb

from obs.api.schemas import OnboardInput
from obs.audit import audit
from obs.db import connection, notify, one
from obs.integrations import aws, http
from obs.integrations.airbyte import Airbyte
from obs.redact import redact
from obs.settings import require_live, settings


def event(tenant: str, step: str, status: str, message: str) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO obs.tenant_events(tenant_id,step,status,message) VALUES(%s,%s,%s,%s)",
            (tenant, step, status, redact(message)),
        )
        notify(conn, "onboarding.step", {"tenant_id": tenant, "step": step, "status": status})


def resource(tenant: str, key: str, create: Callable[[], str]) -> str:
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (tenant + key,))
        saved = conn.execute(
            "SELECT * FROM obs.provisioning_resources WHERE tenant_id=%s AND resource_key=%s",
            (tenant, key),
        ).fetchone()
        if saved:
            if saved["state"] == "ready":
                return saved["remote_id"]
            raise RuntimeError(
                f"Resource {key} needs reconciliation. Check Airbyte and attach the existing ID before retrying the DAG."
            )
        conn.execute(
            "INSERT INTO obs.provisioning_resources(tenant_id,resource_key,state) VALUES(%s,%s,'creating')",
            (tenant, key),
        )
    try:
        remote_id = str(create())
    except Exception:
        with connection() as conn:
            conn.execute(
                "UPDATE obs.provisioning_resources SET state='uncertain',updated_at=now() WHERE tenant_id=%s AND resource_key=%s",
                (tenant, key),
            )
        raise
    with connection() as conn:
        conn.execute(
            "UPDATE obs.provisioning_resources SET state='ready',remote_id=%s,updated_at=now() WHERE tenant_id=%s AND resource_key=%s",
            (remote_id, tenant, key),
        )
    return remote_id


def run(payload: dict) -> None:
    require_live()
    data = OnboardInput.model_validate(payload)
    config, ab = settings(), Airbyte(write=True)
    if (
        not config.airbyte_workspace_id
        or not config.airbyte_destination_id
        or not config.airbyte_config_url
    ):
        raise ValueError(
            "Onboarding requires Airbyte workspace, destination, and OSS config API URL"
        )
    if not one(
        "SELECT 1 FROM obs.tenants WHERE tenant_id=%s AND status='onboarding'", (data.tenant_id,)
    ):
        raise ValueError("Tenant must already be registered with onboarding status")
    mapping = {}
    try:
        for source, enabled, reference in [
            ("mysql", data.has_mysql, data.mysql_secret_ref),
            ("mongo", data.has_mongo, data.mongo_secret_ref),
        ]:
            if not enabled:
                continue
            event(
                data.tenant_id,
                f"Create {source} source",
                "started",
                "Resolving the approved secret reference",
            )
            secret = aws.secret(reference)
            source_config = secret["airbyte_configuration"]
            if not isinstance(source_config, dict) or not source_config.get("sourceType"):
                raise ValueError(
                    "Secret requires a reviewed airbyte_configuration with sourceType matching the deployed connector"
                )
            if source == "mysql":
                expected = {
                    "host": data.mysql_host,
                    "port": data.mysql_port,
                    "database": data.mysql_database,
                    "username": data.mysql_user,
                    "password": secret["password"],
                }
                if any(
                    source_config.get(key, 3306 if key == "port" else None) != value
                    for key, value in expected.items()
                ):
                    raise ValueError(
                        "Airbyte MySQL configuration does not match the source validated by preflight"
                    )
            elif (
                source_config.get("connection_string") != secret.get("uri")
                or secret.get("database") != data.mongo_database
            ):
                raise ValueError(
                    "Airbyte Mongo configuration must match the validated URI and database"
                )
            source_id = resource(
                data.tenant_id,
                source + ":source",
                lambda: ab.call(
                    "POST",
                    "/sources",
                    json={
                        "name": f"obs-{data.tenant_id}-{source}",
                        "workspaceId": config.airbyte_workspace_id,
                        "configuration": source_config,
                    },
                )["sourceId"],
            )
            result = http.request(
                "POST",
                config.airbyte_config_url.rstrip("/") + "/sources/check_connection",
                token=ab.token(),
                safe=True,
                json={"sourceId": source_id},
            )
            if result.get("status") != "succeeded":
                raise RuntimeError(
                    "Airbyte source connection check failed; inspect the source connector settings"
                )
            event(
                data.tenant_id,
                f"Create {source} source",
                "ok",
                "Source created and Airbyte connection check passed",
            )
            for load in ("initial", "cdc"):
                streams = secret[f"{load}_streams"]
                if not isinstance(streams, list) or not streams:
                    raise ValueError(
                        "Secret requires reviewed initial_streams and cdc_streams configurations"
                    )
                event(
                    data.tenant_id,
                    f"Create {source} {load} connection",
                    "started",
                    "Creating a manually scheduled Airbyte connection",
                )
                connection_id = resource(
                    data.tenant_id,
                    source + ":" + load,
                    lambda load=load, streams=streams: ab.call(
                        "POST",
                        "/connections",
                        json={
                            "name": f"obs-{data.tenant_id}-{source}-{load}",
                            "sourceId": source_id,
                            "destinationId": config.airbyte_destination_id,
                            "namespaceDefinition": "custom_format",
                            "namespaceFormat": data.warehouse_schema or data.tenant_id,
                            "schedule": {"scheduleType": "manual"},
                            "configurations": {"streams": streams},
                            "nonBreakingSchemaUpdatesBehavior": "disable_connection",
                        },
                    )["connectionId"],
                )
                mapping[f"{source}_{load}"] = connection_id
                event(
                    data.tenant_id,
                    f"Create {source} {load} connection",
                    "ok",
                    "Connection ID saved durably",
                )
        with connection() as conn:
            conn.execute(
                "UPDATE obs.tenants SET airbyte_connections=%s,updated_at=now() WHERE tenant_id=%s",
                (Jsonb(mapping), data.tenant_id),
            )
        if data.run_initial:
            event(
                data.tenant_id,
                "Run initial loads",
                "started",
                "Waiting for each initial Airbyte job to succeed",
            )
            for key, connection_id in mapping.items():
                if not key.endswith("_initial"):
                    continue
                job_id = int(
                    resource(
                        data.tenant_id,
                        key + ":initial_job",
                        lambda connection_id=connection_id: str(ab.sync(connection_id)["jobId"]),
                    )
                )
                deadline = time.monotonic() + 7200
                while time.monotonic() < deadline:
                    state = ab.call("GET", f"/jobs/{job_id}")["status"]
                    if state == "succeeded":
                        break
                    if state in {"failed", "cancelled"}:
                        raise RuntimeError(
                            f"Initial load {job_id} {state}. Inspect the failed run before resuming onboarding."
                        )
                    time.sleep(15)
                else:
                    raise RuntimeError(f"Initial load {job_id} has not completed within two hours")
            event(data.tenant_id, "Run initial loads", "ok", "Every initial load succeeded")
        with connection() as conn:
            conn.execute(
                "UPDATE obs.tenants SET status='active',updated_at=now() WHERE tenant_id=%s",
                (data.tenant_id,),
            )
            audit(conn, "airflow:onboard_tenant", "activate_tenant", data.tenant_id)
        event(
            data.tenant_id,
            "Activate tenant",
            "ok",
            "Tenant active; runtime registry will include it on the next CDC schedule",
        )
    except Exception as exc:
        event(data.tenant_id, "Onboarding", "failed", redact(str(exc)))
        raise RuntimeError(
            "Onboarding failed. See redacted console events for the recovery step."
        ) from None
