"""Coordinator + two provisioning DAGs. Only workflow references enter DAG conf."""
import json
import os
from datetime import datetime, timedelta, timezone

try:
    from airflow.sdk import dag, task
except ImportError:
    from airflow.decorators import dag, task
from airflow.sensors.base import BaseSensorOperator


def configured_ids():
    values = {"coordinator": os.environ.get("ONBOARDING_DAG_ID", "onboard_tenant"),
              "mysql_provision": "obs_mysql_provision", "mongo_provision": "obs_mongo_provision"}
    values.update(json.loads(os.environ.get("ONBOARDING_DAG_IDS", "{}")))
    return values


def references(context):
    run = context["dag_run"]
    return run.conf or {}, run.dag_id, run.run_id


class WorkflowSensor(BaseSensorOperator):
    def poke(self, context):
        from obs.onboarding.workflow import advance_live, execution
        conf, dag_id, run_id = references(context)
        execution(conf, dag_id, run_id)
        return advance_live(conf["tenant_id"])


@dag(dag_id=configured_ids()["coordinator"], schedule=None,
     start_date=datetime(2025, 1, 1, tzinfo=timezone.utc), catchup=False,
     max_active_runs=8, dagrun_timeout=timedelta(hours=25),
     default_args={"owner": "data-platform", "retries": 0}, tags=["observability", "onboarding"])
def onboarding_coordinator():
    @task(task_id="validate_request", do_xcom_push=False)
    def validate_request(**context):
        from obs.onboarding.workflow import begin_coordinator
        begin_coordinator(*references(context))

    wait = WorkflowSensor(task_id="coordinate_branches", mode="reschedule", poke_interval=30,
                          timeout=86400, pool="obs_workflow", execution_timeout=timedelta(minutes=5))

    @task(task_id="activate_tenant", do_xcom_push=False)
    def activate_tenant(**context):
        from obs.onboarding.workflow import activate, execution
        conf, dag_id, run_id = references(context)
        execution(conf, dag_id, run_id)
        if not activate(conf["tenant_id"]):
            from airflow.exceptions import AirflowSkipException
            raise AirflowSkipException("Initial load deferred; tenant remains onboarding")

    validate_request() >> wait >> activate_tenant()


onboarding_coordinator()


def build_provisioning(source):
    @dag(dag_id=configured_ids()[source + "_provision"], schedule=None,
         start_date=datetime(2025, 1, 1, tzinfo=timezone.utc), catchup=False,
         max_active_runs=8, dagrun_timeout=timedelta(hours=1),
         default_args={"owner": "data-platform", "retries": 0},
         tags=["observability", "onboarding", source, "provisioning"])
    def provision_source():
        previous = None
        for step in ("resolve_secret", "create_source", "check_source", "create_initial_connection", "create_cdc_connection", "save_connections"):
            @task(task_id=step, do_xcom_push=False, execution_timeout=timedelta(minutes=10))
            def provision_step(step_name, **context):
                from obs.provision import source_step
                source_step(*references(context), step_name)
            current = provision_step(step)
            if previous is not None:
                previous >> current
            previous = current
    return provision_source()


for _source in ("mysql", "mongo"):
    globals()["provision_" + _source] = build_provisioning(_source)
