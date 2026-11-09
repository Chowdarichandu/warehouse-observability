import json
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.stub import Stubber
from fastapi import HTTPException
import httpx
import pytest
from pydantic import ValidationError

from obs.alerter import notify
from obs.collector.normalize import failure, normalize, tenant_for
from obs.collector.store import save
from obs.configure import Configuration
from obs.db import connection, one
from obs.integrations import aws, http, warehouse
from obs.integrations.airbyte import Airbyte, duration_seconds
from obs.integrations.airflow import Airflow
from obs.settings import Settings, settings

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture
def live(monkeypatch):
    # Keep the isolated local test DB; emulate validated service configuration.
    config = settings()
    for key, value in {
        "mode": "live",
        "airflow_url": "https://airflow.example.test",
        "airflow_read_token": "reader",
        "airflow_write_token": "writer",
        "airbyte_url": "https://airbyte.example.test/v1",
        "airbyte_token": "ab-reader",
        "airbyte_write_token": "ab-writer",
        "live_actions_enabled": True,
    }.items():
        monkeypatch.setattr(config, key, value)
    return config


def transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(http.time, "sleep", lambda _: None)


@pytest.mark.parametrize(
    "value,expected",
    [("PT4M12S", 252), ("P1DT2H3M4.5S", 93784), (None, None), (24, 24), ("PT0S", 0)],
)
def test_airbyte_duration(value, expected):
    assert duration_seconds(value) == expected


def test_live_configuration_fails_closed():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, mode="live")
    base = {
        "mode": "live",
        "jwt_secret": "a-secure-random-production-signing-key-123",
        "console_url": "https://obs.example.test",
        "database_url": "postgresql://user:password@db/obs?sslmode=verify-full",
        "auth_provider": "oidc",
        "oidc_issuer": "https://id.example.test",
        "oidc_client_id": "client",
        "oidc_group_roles": {"ops": "operator"},
    }
    assert Settings(_env_file=None, **base).mode == "live"
    for change in [
        {"console_url": "http://obs.example.test"},
        {"cookie_secure": False},
        {"auth_provider": "local"},
        {"oidc_group_roles": {}},
        {"database_url": "postgresql://db/obs"},
        {"airflow_url": "http://airflow"},
    ]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **(base | change))


def test_demo_blocks_all_live_entry_points():
    with pytest.raises(RuntimeError):
        Airflow()
    with pytest.raises(RuntimeError):
        Airbyte()
    with pytest.raises(RuntimeError):
        aws.client("sns")
    with pytest.raises(RuntimeError):
        warehouse.connect()


def test_http_safe_reads_retry_but_mutations_do_not(live, monkeypatch):
    methods = []

    def handler(request):
        methods.append(request.method)
        return httpx.Response(503, json={})

    transport(monkeypatch, handler)
    with pytest.raises(http.UpstreamError) as read:
        http.request("GET", "https://upstream.example.test")
    assert methods == ["GET"] * 3
    assert not read.value.ambiguous
    methods.clear()
    with pytest.raises(http.UpstreamError) as write:
        http.request("POST", "https://upstream.example.test", json={})
    assert methods == ["POST"]
    assert write.value.ambiguous


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_airflow_version_auth_pagination_and_scoped_retry(live, monkeypatch, version):
    monkeypatch.setattr(live, "airflow_api_version", version)
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == "POST":
            assert request.headers["authorization"] == "Bearer writer"
            body = json.loads(request.content)
            assert body["dag_run_id"] == "specific-run"
            assert body["only_failed"] is True and body["dry_run"] is False
            assert not any(
                body[k]
                for k in (
                    "include_upstream",
                    "include_downstream",
                    "include_past",
                    "include_future",
                )
            )
            assert body["task_ids"] == ([["sync", 4]] if version == "v2" else ["sync"])
            return httpx.Response(200, json={"task_instances": []})
        assert request.headers["authorization"] == "Bearer reader"
        assert request.url.path.startswith(f"/api/{version}/")
        return httpx.Response(200, json={"task_instances": [], "total_entries": 0})

    transport(monkeypatch, handler)
    assert Airflow().tasks("mysql_cdc", "run/with space") == []
    task = {
        "dag_id": "mysql_cdc",
        "dag_run_id": "specific-run",
        "task_id": "sync",
        "map_index": 4 if version == "v2" else -1,
    }
    Airflow(write=True).retry(task)
    with pytest.raises(ValueError, match="cannot mutate"):
        Airflow().call("PATCH", "/dags/mysql_cdc", body={})
    with pytest.raises(ValueError, match="allowlist"):
        Airflow(write=True).retry(task | {"dag_id": "unapproved"})
    if version == "v1":
        with pytest.raises(ValueError, match="map index"):
            Airflow(write=True).retry(task | {"map_index": 4})
    assert len(calls) == 2


def test_mwaa_uses_iam_request_contract(live, monkeypatch):
    monkeypatch.setattr(live, "airflow_transport", "mwaa")
    monkeypatch.setattr(live, "mwaa_environment", "staging-airflow")
    client = boto3.client(
        "mwaa",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    with Stubber(client) as stub:
        stub.add_response(
            "invoke_rest_api",
            {
                "RestApiStatusCode": 200,
                "RestApiResponse": {"scheduler": {"status": "healthy"}},
            },
            {"Name": "staging-airflow", "Method": "GET", "Path": "/health"},
        )
        monkeypatch.setattr(aws, "client", lambda *args, **kwargs: client)
        assert Airflow().health()["scheduler"]["status"] == "healthy"
        stub.assert_no_pending_responses()


def test_linker_status_precedence_resolution_and_stats():
    task = json.loads((FIXTURES / "airflow-task.json").read_text())
    job = json.loads((FIXTURES / "airbyte-job.json").read_text())
    tenants = [
        {
            "tenant_id": "acme_retail",
            "warehouse_schema": "acme",
            "airbyte_connections": {"mysql_cdc": job["connectionId"]},
        }
    ]
    assert (
        tenant_for(task, job, tenants, r"sync_(?P<tenant>.*)")["tenant_id"]
        == "acme_retail"
    )
    run = normalize(task, job, "acme_retail", "mysql", "cdc")
    assert run["status"] == "failed" and run["failed_stage"] == "airbyte"
    assert run["queue_delay_s"] == 30 and run["duration_s"] == 240
    assert (
        normalize(task, job | {"status": "succeeded"}, "acme_retail", "mysql", "cdc")[
            "failed_stage"
        ]
        == "airflow"
    )
    assert (
        normalize(
            task | {"state": "success"},
            job | {"status": "running"},
            "acme_retail",
            "mysql",
            "cdc",
        )["status"]
        == "running"
    )
    assert (
        normalize(None, job, "acme_retail", "mysql", "cdc")["run_key"]
        == f"airbyte|{job['jobId']}"
    )
    assert failure(job)[3][0]["streamName"] == "orders"
    with pytest.raises(ValueError, match="multiple tenants"):
        tenant_for(
            task,
            job,
            tenants + [tenants[0] | {"tenant_id": "other"}],
            r"sync_(?P<tenant>.*)",
        )


def test_ingest_is_idempotent_links_existing_job_and_redacts():
    task = json.loads((FIXTURES / "airflow-task.json").read_text())
    job = json.loads((FIXTURES / "airbyte-job.json").read_text())
    job["jobId"] = int(uuid4().int % 10000000000) + 10000000000
    task["dag_run_id"] += str(uuid4())
    message, origin, log, streams = failure(job)
    standalone = normalize(None, job, "acme_retail", "mysql", "cdc")
    linked = normalize(task, job, "acme_retail", "mysql", "cdc")
    try:
        with connection() as conn:
            save(
                conn,
                standalone,
                message=message,
                origin=origin,
                log=log,
                streams=streams,
            )
            save(conn, linked, message=message, origin=origin, log=log, streams=streams)
            save(conn, linked, message=message, origin=origin, log=log, streams=streams)
        assert (
            one(
                "SELECT count(*) AS n FROM obs.pipeline_runs WHERE airbyte_job_id=%s",
                (job["jobId"],),
            )["n"]
            == 1
        )
        stored = one(
            "SELECT content FROM obs.run_logs WHERE run_key=%s", (linked["run_key"],)
        )["content"]
        assert "hidden-token" not in stored
        error = one(
            "SELECT error_message FROM obs.run_errors WHERE run_key=%s",
            (linked["run_key"],),
        )["error_message"]
        assert "hidden-secret" not in error and "ops@example.org" not in error
        assert (
            one(
                "SELECT records FROM obs.run_stream_stats WHERE run_key=%s",
                (linked["run_key"],),
            )["records"]
            == 42
        )
    finally:
        with connection() as conn:
            conn.execute(
                "DELETE FROM obs.pipeline_runs WHERE airbyte_job_id=%s", (job["jobId"],)
            )


def test_secret_namespace_and_aws_shape(live, monkeypatch):
    client = boto3.client(
        "secretsmanager",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    with Stubber(client) as stub:
        stub.add_response(
            "get_secret_value",
            {"SecretString": '{"password":"private"}'},
            {"SecretId": "observability/tenant/mysql"},
        )
        monkeypatch.setattr(aws, "client", lambda *args, **kwargs: client)
        assert aws.secret("aws://observability/tenant/mysql") == {"password": "private"}
        with pytest.raises(ValueError):
            aws.secret("aws://outside/mysql")
        with pytest.raises(ValueError):
            aws.secret("demo://tenant/mysql")
        stub.assert_no_pending_responses()


def test_notification_sns_contract_and_no_demo_network(live, monkeypatch):
    topic = "arn:aws:sns:us-east-1:123456789012:observability"
    monkeypatch.setenv("TEST_SNS_TOPIC", topic)
    aws.environment_secret.cache_clear()
    client = boto3.client(
        "sns",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    with Stubber(client) as stub:
        stub.add_response(
            "publish",
            {"MessageId": "test-message"},
            {
                "TopicArn": topic,
                "Subject": "Test alert",
                "Message": "Test alert\nDetails",
            },
        )
        monkeypatch.setattr(aws, "client", lambda *args, **kwargs: client)
        notify.send(
            {
                "id": 1,
                "channel_kind": "sns",
                "target_env": "TEST_SNS_TOPIC",
                "message": "Test alert\nDetails",
            }
        )
        monkeypatch.setattr(live, "mode", "demo")
        with pytest.raises(RuntimeError):
            notify.send({"channel_kind": "sns"})
        stub.assert_no_pending_responses()
    aws.environment_secret.cache_clear()


def test_webhooks_reject_unapproved_hosts(live, monkeypatch):
    monkeypatch.setenv(
        "TEST_WEBHOOK", "https://unapproved.example.test/hook/private-token"
    )
    aws.environment_secret.cache_clear()
    with pytest.raises(ValueError, match="configured"):
        notify.send(
            {
                "id": 1,
                "channel_kind": "slack",
                "target_env": "TEST_WEBHOOK",
                "message": "Test",
            }
        )
    aws.environment_secret.cache_clear()


def test_registry_rejects_duplicate_connections():
    tenant = {
        "tenant_id": "sample_tenant",
        "display_name": "Sample",
        "warehouse_schema": "sample",
        "has_mongo": False,
        "airbyte_connections": {"mysql_initial": "same", "mysql_cdc": "same"},
    }
    with pytest.raises(ValidationError, match="unique"):
        Configuration.model_validate({"tenants": [tenant]})


def test_actions_disabled_before_any_external_request(live, monkeypatch):
    from obs.actions.live import retry

    monkeypatch.setattr(live, "live_actions_enabled", False)
    with pytest.raises(HTTPException) as error:
        retry("missing", "operator")
    assert error.value.status_code == 403


def test_demo_entrypoint_never_fetches_aws_secret(monkeypatch):
    import sys
    from obs.entrypoint import main

    monkeypatch.setenv("MODE", "demo")
    monkeypatch.setenv("OBS_CONFIG_SECRET_ID", "observability/api")
    monkeypatch.setattr(
        sys, "argv", ["obs.entrypoint", "--", "python", "-m", "obs.collector"]
    )
    monkeypatch.setattr(
        boto3,
        "client",
        lambda *args, **kwargs: pytest.fail("Demo bootstrap contacted AWS"),
    )
    executed = []
    monkeypatch.setattr("os.execvpe", lambda *args: executed.append(args[0]))
    main()
    assert executed == ["python"]
