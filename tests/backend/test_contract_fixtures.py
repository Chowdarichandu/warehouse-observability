"""Contract tests replaying the recorded, sanitized fixtures in
tests/fixtures through the Airflow (2.x and 3.x) and Airbyte clients.

Every supported version and endpoint family has a fixture. Tests use an
HTTP MockTransport; no live endpoints are contacted and no database is
needed.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from obs.integrations import http
from obs.integrations.airbyte import Airbyte, duration_seconds
from obs.integrations.airflow import Airflow
from obs.settings import settings

FIXTURES = Path(__file__).parents[1] / "fixtures"
SINCE = datetime(2026, 11, 9, tzinfo=UTC)


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture()
def live_config(monkeypatch):
    config = settings()
    for key, value in {
        "mode": "live",
        "airflow_url": "https://airflow.example.test",
        "airflow_read_token": "reader",
        "airflow_write_token": "writer",
        "airbyte_url": "https://airbyte.example.test/api/public/v1",
        "airbyte_token": "ab-reader",
        "airbyte_write_token": "ab-writer",
        "airbyte_config_url": "https://airbyte.example.test/api/v1",
        "live_actions_enabled": True,
    }.items():
        monkeypatch.setattr(config, key, value)
    return config


def transport(monkeypatch, handler) -> None:
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(http.time, "sleep", lambda _: None)


def airflow_handler(version: str, seen: list[str]):
    fixtures = {
        "xcomEntries": "airflow-xcom-return-value.json",
        "/taskInstances": f"airflow-{version}-task-instances.json",
        "dagRuns": f"airflow-{version}-dag-runs.json",
        "/monitor/health": "airflow-v2-health.json",
        "/health": "airflow-v1-health.json",
        "/pools": "airflow-pools.json",
        "/importErrors": "airflow-import-errors.json",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        for marker, name in fixtures.items():
            if marker in request.url.path:
                return httpx.Response(200, json=load(name))
        return httpx.Response(404, json={"detail": "not found"})

    return handler


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_airflow_dag_runs_fixture_parses_per_version(live_config, monkeypatch, version):
    monkeypatch.setattr(live_config, "airflow_api_version", version)
    seen: list[str] = []
    transport(monkeypatch, airflow_handler(version, seen))
    runs = Airflow().runs("mysql_cdc", SINCE)
    # The three watermark filter queries merge into one run.
    assert [run["dag_run_id"] for run in runs] == [
        "scheduled__2026-11-09T01:00:00+00:00"
    ]
    assert runs[0]["state"] == "failed"
    filter_param = "execution_date_gte" if version == "v1" else "run_after_gte"
    assert any(filter_param in url for url in seen)


@pytest.mark.parametrize(
    "version,count",
    [("v1", 2), ("v2", 1)],
)
def test_airflow_task_instances_fixture_parses_per_version(
    live_config, monkeypatch, version, count
):
    monkeypatch.setattr(live_config, "airflow_api_version", version)
    transport(monkeypatch, airflow_handler(version, []))
    tasks = Airflow().tasks("mysql_cdc", "scheduled__2026-11-09T01:00:00+00:00")
    assert len(tasks) == count
    assert tasks[0]["task_id"] == "sync_acme_retail"
    assert tasks[0]["state"] == "failed"


def test_airflow_xcom_fixture_yields_the_airbyte_job_id(live_config, monkeypatch):
    transport(monkeypatch, airflow_handler("v1", []))
    task = load("airflow-v1-task-instances.json")["task_instances"][0]
    assert Airflow().job_id(task) == 987654321


@pytest.mark.parametrize(
    "version,path,extra_keys",
    [
        ("v1", "/health", set()),
        ("v2", "/monitor/health", {"dag_processor", "triggerer"}),
    ],
)
def test_airflow_health_fixture_per_version(
    live_config, monkeypatch, version, path, extra_keys
):
    monkeypatch.setattr(live_config, "airflow_api_version", version)
    seen: list[str] = []
    transport(monkeypatch, airflow_handler(version, seen))
    health = Airflow().health()
    assert health["metadatabase"]["status"] == "healthy"
    assert set(health) >= {"metadatabase", "scheduler"} | extra_keys
    assert any(path in url for url in seen)


def test_airflow_pools_and_import_errors_fixtures(live_config, monkeypatch):
    transport(monkeypatch, airflow_handler("v1", []))
    client = Airflow()
    pools = client.pages("/pools", "pools")
    assert pools[0]["name"] == "default_pool"
    assert pools[0]["open_slots"] == 125
    errors = client.pages("/importErrors", "import_errors")
    assert errors[0]["import_error_id"] == 7
    assert "missing_module" in errors[0]["stack_trace"]


def airbyte_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/jobs/get"):
        return httpx.Response(200, json=load("airbyte-config-job.json"))
    if request.url.path.endswith("/jobs"):
        return httpx.Response(200, json=load("airbyte-jobs-list.json"))
    if "/jobs/" in request.url.path:
        return httpx.Response(200, json=load("airbyte-job.json"))
    return httpx.Response(404, json={"detail": "not found"})


def test_airbyte_jobs_list_fixture_parses(live_config, monkeypatch):
    transport(monkeypatch, airbyte_handler)
    jobs = Airbyte().jobs("11111111-1111-4111-8111-111111111111", SINCE)
    assert [job["jobId"] for job in jobs] == [987654321, 987654322]
    assert duration_seconds(jobs[0]["duration"]) == 238
    assert jobs[1]["status"] == "succeeded"


def test_airbyte_job_detail_merges_config_api_attempts(live_config, monkeypatch):
    transport(monkeypatch, airbyte_handler)
    job = Airbyte().job(987654321)
    assert job["status"] == "failed"
    attempts = job["attempts_detail"]
    failure = attempts[0]["attempt"]["failureSummary"]["failures"][0]
    assert failure["failureOrigin"] == "source"
    stats = attempts[0]["output"]["sync"]["streamStats"][0]
    assert stats["streamName"] == "orders"
    assert stats["stats"]["recordsCommitted"] == 42
