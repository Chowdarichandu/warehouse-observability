"""Requires the obs-console wheel and its pinned dependencies on all Airflow workers."""
from datetime import datetime, timedelta, timezone

try:
    from airflow.sdk import dag, task
except ImportError:
    from airflow.decorators import dag, task


@dag(dag_id="onboard_tenant", schedule=None, start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
     catchup=False, max_active_runs=1, dagrun_timeout=timedelta(hours=3),
     default_args={"owner": "data-platform", "retries": 0}, tags=["observability", "onboarding"])
def onboarding():
    @task(task_id="provision", do_xcom_push=False, execution_timeout=timedelta(hours=3))
    def provision(**context):
        # Only secret references are accepted in dag_run.conf; raw credentials never reach XCom.
        from obs.provision import run
        run(context["dag_run"].conf)
    provision()


onboarding()
