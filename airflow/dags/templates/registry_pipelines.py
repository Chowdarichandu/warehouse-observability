"""Four sync DAGs: scoped onboarding invocations or active-tenant CDC schedules."""
import json
import os
from datetime import datetime, timedelta, timezone

try:
    from airflow.sdk import dag, task
except ImportError:
    from airflow.decorators import dag, task
from airflow.providers.airbyte.sensors.airbyte import AirbyteJobSensor


def configured_ids():
    # Existing team's IDs remain configuration. Defaults are prefixed reference
    # DAGs; set AIRFLOW_DAGS and ONBOARDING_DAG_IDS consistently before cutover.
    values = {f"{s}_{load}": f"obs_{s}_{load}" for s in ("mysql", "mongo") for load in ("initial", "cdc")}
    values.update(json.loads(os.environ.get("AIRFLOW_DAGS", "{}")))
    values.update({key: value for key, value in json.loads(os.environ.get("ONBOARDING_DAG_IDS", "{}" )).items() if key in values})
    return values


def build_pipeline(dag_id, source, load):
    @dag(dag_id=dag_id, schedule="@hourly" if load == "cdc" else None,
         start_date=datetime(2025, 1, 1, tzinfo=timezone.utc), catchup=False,
         max_active_runs=8, dagrun_timeout=timedelta(hours=3),
         default_args={"owner": "data-platform", "retries": 0}, tags=["observability", source, load])
    def pipeline():
        @task(task_id="resolve_connections")
        def resolve_connections(**context):
            conf = context["dag_run"].conf or {}
            if conf.get("workflow_id"):
                from obs.provision import sync_connection
                run = context["dag_run"]
                return sync_connection(conf, run.dag_id, run.run_id, source, load)
            import psycopg
            from psycopg.rows import dict_row
            key = f"{source}_{load}"
            with psycopg.connect(os.environ["OBS_DATABASE_URL"], row_factory=dict_row, connect_timeout=5) as conn:
                return [row["connection_id"] for row in conn.execute(
                    "SELECT airbyte_connections->>%s AS connection_id FROM obs.tenants WHERE status='active' AND airbyte_connections ? %s ORDER BY tenant_id", (key, key)).fetchall()]

        @task(task_id="sync", pool="airbyte_sync", execution_timeout=timedelta(minutes=10))
        def sync(connection_id, **context):
            conf = context["dag_run"].conf or {}
            if conf.get("workflow_id"):
                from obs.provision import trigger_onboarding_sync
                run = context["dag_run"]
                return trigger_onboarding_sync(conf, run.dag_id, run.run_id, connection_id)
            from airflow.providers.airbyte.hooks.airbyte import AirbyteHook
            result = AirbyteHook(airbyte_conn_id="airbyte_operations").submit_sync_connection(connection_id)
            return int(result.job_id)

        jobs = sync.expand(connection_id=resolve_connections())
        AirbyteJobSensor.partial(task_id="wait_for_sync", airbyte_conn_id="airbyte_operations", mode="reschedule",
                                 poke_interval=30, timeout=7200, pool="airbyte_wait").expand(airbyte_job_id=jobs)
    return pipeline()


for _source in ("mysql", "mongo"):
    for _load in ("initial", "cdc"):
        _key = f"{_source}_{_load}"
        globals()[_key] = build_pipeline(configured_ids()[_key], _source, _load)
