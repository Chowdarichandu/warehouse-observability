"""Airflow 2.9+/3 reference DAGs. Deploy only after renaming existing DAGs in review."""
from datetime import datetime, timedelta, timezone

try:
    from airflow.sdk import dag, task
except ImportError:
    from airflow.decorators import dag, task
from airflow.providers.airbyte.operators.airbyte import AirbyteTriggerSyncOperator
from airflow.providers.airbyte.sensors.airbyte import AirbyteJobSensor


def build_pipeline(dag_id: str, source: str, load: str):
    @dag(dag_id=dag_id, schedule="@hourly" if load == "cdc" else None,
         start_date=datetime(2025, 1, 1, tzinfo=timezone.utc), catchup=False,
         max_active_runs=1, dagrun_timeout=timedelta(hours=3),
         default_args={"owner": "data-platform", "retries": 0}, tags=["observability", source, load])
    def pipeline():
        @task
        def get_active_tenants() -> list[str]:
            # Runtime query only. Configure OBS_DATABASE_URL as an Airflow secret-backed env var.
            import os
            import psycopg
            from psycopg.rows import dict_row
            pipeline_key = f"{source}_{load}"
            with psycopg.connect(os.environ["OBS_DATABASE_URL"], row_factory=dict_row, connect_timeout=5) as conn:
                return [row["connection_id"] for row in conn.execute(
                    "SELECT airbyte_connections->>%s AS connection_id FROM obs.tenants WHERE status='active' AND airbyte_connections ? %s ORDER BY tenant_id",
                    (pipeline_key, pipeline_key)).fetchall()]

        sync = AirbyteTriggerSyncOperator.partial(
            task_id="sync", airbyte_conn_id="airbyte_operations", asynchronous=True,
            execution_timeout=timedelta(minutes=10), pool="airbyte_sync", do_xcom_push=True,
        ).expand(connection_id=get_active_tenants())
        AirbyteJobSensor.partial(
            task_id="wait_for_sync", airbyte_conn_id="airbyte_operations", mode="reschedule",
            poke_interval=30, timeout=7200, pool="airbyte_wait",
        ).expand(airbyte_job_id=sync.output)
    return pipeline()


# Prefix prevents accidentally replacing the team's current DAG definitions.
for _source in ("mysql", "mongo"):
    for _load in ("initial", "cdc"):
        _id = f"obs_{_source}_{_load}"
        globals()[_id] = build_pipeline(_id, _source, _load)
