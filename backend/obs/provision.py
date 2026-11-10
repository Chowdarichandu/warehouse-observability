"""One-source provisioning tasks for the reviewed seven-DAG workflow."""

from collections.abc import Callable

from psycopg.types.json import Jsonb

from obs.api.schemas import OnboardInput
from obs.db import connection, one
from obs.integrations import aws, http
from obs.integrations.airbyte import Airbyte
from obs.onboarding import workflow
from obs.redact import redact
from obs.settings import require_live, settings


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
            if saved["state"] != "failed":
                raise RuntimeError(
                    f"Resource {key} requires reconciliation; attach the confirmed upstream ID before resuming."
                )
            conn.execute(
                "UPDATE obs.provisioning_resources SET state='creating',updated_at=now() WHERE tenant_id=%s AND resource_key=%s",
                (tenant, key),
            )
        else:
            conn.execute(
                "INSERT INTO obs.provisioning_resources(tenant_id,resource_key,state) VALUES(%s,%s,'creating')",
                (tenant, key),
            )
    try:
        remote_id = str(create())
        if not remote_id or remote_id == "None":
            raise RuntimeError("Upstream create did not return a resource ID")
    except Exception as exc:
        confirmed = isinstance(exc, http.UpstreamError) and not exc.ambiguous
        with connection() as conn:
            conn.execute(
                "UPDATE obs.provisioning_resources SET state=%s,updated_at=now() WHERE tenant_id=%s AND resource_key=%s",
                ("failed" if confirmed else "uncertain", tenant, key),
            )
        raise
    with connection() as conn:
        conn.execute(
            "UPDATE obs.provisioning_resources SET state='ready',remote_id=%s,updated_at=now() WHERE tenant_id=%s AND resource_key=%s",
            (remote_id, tenant, key),
        )
    return remote_id


def _source_config(data: OnboardInput, source: str) -> tuple[dict, dict]:
    secret = aws.secret(getattr(data, source + "_secret_ref"))
    config = secret["airbyte_configuration"]
    if not isinstance(config, dict) or not config.get("sourceType"):
        raise ValueError("Secret requires a reviewed Airbyte connector configuration")
    if source == "mysql":
        expected = {
            "host": data.mysql_host,
            "port": data.mysql_port,
            "database": data.mysql_database,
            "username": data.mysql_user,
            "password": secret["password"],
        }
        if any(
            config.get(key, 3306 if key == "port" else None) != value
            for key, value in expected.items()
        ):
            raise ValueError(
                "MySQL connector configuration differs from preflight-validated source"
            )
    elif (
        config.get("connection_string") != secret.get("uri")
        or secret.get("database") != data.mongo_database
    ):
        raise ValueError("MongoDB connector configuration differs from preflight-validated source")
    for load in ("initial", "cdc"):
        if not isinstance(secret.get(f"{load}_streams"), list) or not secret[f"{load}_streams"]:
            raise ValueError("Secret requires reviewed initial_streams and cdc_streams")
    return secret, config


def _saved(tenant: str, key: str) -> str:
    saved = one(
        "SELECT remote_id FROM obs.provisioning_resources WHERE tenant_id=%s AND resource_key=%s AND state='ready'",
        (tenant, key),
    )
    if not saved:
        raise RuntimeError(f"Provisioning dependency {key} is not ready")
    return saved["remote_id"]


def source_step(conf: dict, dag_id: str, run_id: str, step: str) -> None:
    require_live()
    node, payload = workflow.execution(conf, dag_id, run_id)
    source, phase = node["node_id"].split("_", 1)
    if phase != "provision" or step not in {key for key, _ in workflow.TASKS["provision"]}:
        raise ValueError("Expected a source provisioning task")
    data = OnboardInput.model_validate(payload)
    if not getattr(data, f"has_{source}"):
        raise ValueError("Source is disabled")
    with connection() as conn:
        workflow.update_node(conn, conf["workflow_id"], node["node_id"], "running")
        workflow.task_state(conn, conf["workflow_id"], node["node_id"], step, "running")
    try:
        config = settings()
        if (
            not config.airbyte_workspace_id
            or not config.airbyte_destination_id
            or not config.airbyte_config_url
        ):
            raise ValueError("Airbyte workspace, destination and OSS config API are required")
        secret, source_config = _source_config(data, source)
        ab = Airbyte(write=True)
        if step == "create_source":
            resource(
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
        elif step == "check_source":
            source_id = _saved(data.tenant_id, source + ":source")
            result = http.request(
                "POST",
                config.airbyte_config_url.rstrip("/") + "/sources/check_connection",
                token=ab.token(),
                safe=True,
                json={"sourceId": source_id},
            )
            if result.get("status") != "succeeded":
                raise RuntimeError("Airbyte source connection check failed")
        elif step in {"create_initial_connection", "create_cdc_connection"}:
            load = "initial" if step == "create_initial_connection" else "cdc"
            source_id = _saved(data.tenant_id, source + ":source")
            resource(
                data.tenant_id,
                source + ":" + load,
                lambda: ab.call(
                    "POST",
                    "/connections",
                    json={
                        "name": f"obs-{data.tenant_id}-{source}-{load}",
                        "sourceId": source_id,
                        "destinationId": config.airbyte_destination_id,
                        "namespaceDefinition": "custom_format",
                        "namespaceFormat": data.warehouse_schema or data.tenant_id,
                        "schedule": {"scheduleType": "manual"},
                        "configurations": {"streams": secret[f"{load}_streams"]},
                        "nonBreakingSchemaUpdatesBehavior": "disable_connection",
                    },
                )["connectionId"],
            )
        elif step == "save_connections":
            mapping = {
                f"{source}_{load}": _saved(data.tenant_id, source + ":" + load)
                for load in ("initial", "cdc")
            }
            with connection() as conn:
                # Parallel branches merge atomically instead of overwriting one another.
                conn.execute(
                    "UPDATE obs.tenants SET airbyte_connections=airbyte_connections||%s,updated_at=now() WHERE tenant_id=%s",
                    (Jsonb(mapping), data.tenant_id),
                )
        with connection() as conn:
            workflow.task_state(conn, conf["workflow_id"], node["node_id"], step, "success")
    except Exception as exc:
        with connection() as conn:
            workflow.task_state(
                conn, conf["workflow_id"], node["node_id"], step, "failed", error=str(exc)
            )
            uncertain = conn.execute(
                "SELECT 1 FROM obs.provisioning_resources WHERE tenant_id=%s AND state IN ('creating','uncertain') LIMIT 1",
                (data.tenant_id,),
            ).fetchone()
            state = "uncertain" if uncertain else "failed"
            workflow.update_node(conn, conf["workflow_id"], node["node_id"], state, error=str(exc))
            conn.execute(
                "UPDATE obs.onboarding_workflows SET state=%s WHERE workflow_id=%s",
                (state, conf["workflow_id"]),
            )
        raise RuntimeError(redact(str(exc))) from None


def sync_connection(conf: dict, dag_id: str, run_id: str, source: str, load: str) -> list[str]:
    node, payload = workflow.execution(conf, dag_id, run_id)
    if node["node_id"] != f"{source}_{load}" or not payload["run_initial"]:
        raise ValueError("Sync DAG does not match the enabled onboarding phase")
    with connection() as conn:
        states = {n["node_id"]: n["status"] for n in workflow.latest(conn, conf["workflow_id"])}
        # The first CDC run is blocked until this branch's initial DAG succeeds.
        dependency = f"{source}_provision" if load == "initial" else f"{source}_initial"
        if states[dependency] != "success":
            raise ValueError("Onboarding dependency has not succeeded")
    mapping = one(
        "SELECT airbyte_connections FROM obs.tenants WHERE tenant_id=%s", (payload["tenant_id"],)
    )["airbyte_connections"]
    return [mapping[f"{source}_{load}"]]


def trigger_onboarding_sync(conf: dict, dag_id: str, run_id: str, connection_id: str) -> int:
    node, payload = workflow.execution(conf, dag_id, run_id)
    key = f"{node['node_id']}:sync:a{node['attempt']}"
    return int(
        resource(
            payload["tenant_id"], key, lambda: str(Airbyte(write=True).sync(connection_id)["jobId"])
        )
    )


def run(payload: dict) -> None:
    raise ValueError(
        "Use the reviewed seven-DAG workflow and source_step; monolithic provisioning is disabled"
    )
