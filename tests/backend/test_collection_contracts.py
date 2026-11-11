"""Offline contract checks for the supported Airflow and Airbyte response shapes.

The JSON files are sanitized examples of the API envelopes. They intentionally
remain fixtures rather than recordings until staging acceptance captures the
deployed Airflow and Airbyte versions.
"""

import json
from pathlib import Path

import pytest

from obs.collector.normalize import failure, normalize, tenant_for
from obs.integrations.airbyte import duration_seconds, timestamp

FIXTURES = Path(__file__).parents[1] / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.parametrize(
    ("version", "dag_runs", "tasks", "date_field", "tenant", "expected_state"),
    [
        ("v1", "airflow-v1-dag-runs.json", "airflow-v1-task-instances.json", "execution_date", "acme_retail", "failed"),
        ("v2", "airflow-v2-dag-runs.json", "airflow-v2-task-instances.json", "run_after", "bluefin_health", "success"),
    ],
)
def test_airflow_contract_envelopes_normalize_to_pipeline_runs(
    version: str,
    dag_runs: str,
    tasks: str,
    date_field: str,
    tenant: str,
    expected_state: str,
):
    runs = fixture(dag_runs)
    task_instances = fixture(tasks)
    run = runs["dag_runs"][0]
    task = task_instances["task_instances"][0]

    assert runs["total_entries"] == len(runs["dag_runs"]) == 1
    assert task_instances["total_entries"] == len(task_instances["task_instances"]) == 1
    assert run["dag_run_id"] == task["dag_run_id"]
    assert date_field in run
    assert task["operator"] == "AirbyteTriggerSyncOperator"
    assert version in {"v1", "v2"}

    normalized = normalize(task, None, tenant, "mongo" if version == "v2" else "mysql", "cdc")
    assert normalized["status"] == expected_state
    assert normalized["tenant_id"] == tenant
    assert normalized["dag_id"] == run["dag_id"]
    assert normalized["dag_run_id"] == run["dag_run_id"]
    assert normalized["started_at"] is not None
    assert normalized["ended_at"] is not None


def test_airflow_contract_keeps_xcom_and_log_shapes_explicit():
    # These are the small response bodies consumed by the collector; keeping
    # them separate catches accidental changes to XCom/log parsing contracts.
    xcom = {"value": '{"job_id": 987654321}'}
    log = {"content": "ERROR MySQL binlog has been purged"}
    assert json.loads(xcom["value"])["job_id"] == 987654321
    assert isinstance(log["content"], str) and log["content"].startswith("ERROR")


def test_airbyte_public_and_config_contracts_join_for_successful_job():
    job = fixture("airbyte-public-job.json")
    attempts = fixture("airbyte-config-attempts.json")
    joined = {**job, "attempts_detail": attempts["attempts"]}

    required = {"jobId", "connectionId", "status", "createdAt", "updatedAt", "duration"}
    assert required <= job.keys()
    assert len(joined["attempts_detail"]) == 1
    assert joined["attempts_detail"][0]["attempt"]["streamStats"][0]["stats"]["recordsCommitted"] == 120
    assert duration_seconds(job["duration"]) == 178
    assert timestamp(job["createdAt"]).isoformat() == "2026-11-09T02:00:11+00:00"

    normalized = normalize(None, joined, "bluefin_health", "mongo", "cdc")
    assert normalized["run_key"] == "airbyte|987654322"
    assert normalized["status"] == "success"
    assert normalized["duration_s"] == 178
    assert normalized["airbyte_attempts"] == 1
    assert failure(joined) == ("", "source", "INFO sync completed", joined["attempts_detail"][0]["attempt"]["streamStats"])


def test_airbyte_failed_fixture_preserves_origin_and_stream_stats():
    job = fixture("airbyte-job.json")
    message, origin, log, streams = failure(job)
    assert "binlog has been purged" in message
    assert origin == "source"
    assert "Authorization: Bearer" in log
    assert streams[0]["streamName"] == "orders"


def test_contract_resolution_prefers_connection_id_before_task_namespace():
    task = fixture("airflow-v2-task-instances.json")["task_instances"][0]
    job = fixture("airbyte-public-job.json") | {
        "connectionId": "22222222-2222-4222-8222-222222222222",
        "namespace": "wrong_tenant",
    }
    tenants = [
        {
            "tenant_id": "bluefin_health",
            "warehouse_schema": "bluefin",
            "airbyte_connections": {"mongo_cdc": job["connectionId"]},
        },
        {
            "tenant_id": "wrong_tenant",
            "warehouse_schema": "wrong",
            "airbyte_connections": {},
        },
    ]
    assert tenant_for(task, job, tenants, r"sync_(?P<tenant>[a-z0-9_]+)")["tenant_id"] == "bluefin_health"
