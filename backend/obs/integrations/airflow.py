import base64
import json
from datetime import datetime
from urllib.parse import quote

from obs.integrations import aws, http
from obs.settings import require_live, settings


def part(value: str) -> str:
    return quote(value, safe="")


class Airflow:
    def __init__(self, *, write: bool = False):
        require_live()
        self.write = write
        self.config = settings()
        if (
            write
            and self.config.airflow_transport == "mwaa"
            and not self.config.mwaa_write_role_arn
        ):
            raise ValueError("MWAA writes require a separate MWAA_WRITE_ROLE_ARN")

    def call(
        self, method: str, path: str, *, params: dict | None = None, body: dict | None = None
    ) -> dict:
        require_live()
        if method != "GET" and not self.write:
            raise ValueError("Collector credential cannot mutate Airflow")
        if self.config.airflow_transport == "mwaa":
            if not self.config.mwaa_environment:
                raise ValueError("MWAA_ENVIRONMENT is required")
            payload = {"Name": self.config.mwaa_environment, "Method": method, "Path": path}
            if params:
                payload["QueryParameters"] = params
            if body is not None:
                payload["Body"] = body
            response = aws.client("mwaa", write=self.write).invoke_rest_api(**payload)
            status = response["RestApiStatusCode"]
            if not 200 <= status < 300:
                raise http.UpstreamError(status, ambiguous=method != "GET" and status >= 500)
            result = response["RestApiResponse"]
            return json.loads(result) if isinstance(result, str) else result
        if not self.config.airflow_url:
            raise ValueError("AIRFLOW_URL is required")
        if self.config.airflow_auth_method == "basic":
            username = (
                self.config.airflow_write_username
                if self.write
                else self.config.airflow_read_username
            )
            password = (
                self.config.airflow_write_password
                if self.write
                else self.config.airflow_read_password
            )
            if not username or not password:
                raise ValueError("Separate Airflow read/write Basic credentials are required")
            credential = base64.b64encode(f"{username}:{password}".encode()).decode()
            return http.request(
                method,
                f"{self.config.airflow_url.rstrip('/')}/api/{self.config.airflow_api_version}{path}",
                headers={"Authorization": f"Basic {credential}"},
                params=params,
                json=body,
            )
        token = self.config.airflow_write_token if self.write else self.config.airflow_read_token
        if not token:
            raise ValueError("Separate Airflow read/write bearer credentials are required")
        return http.request(
            method,
            f"{self.config.airflow_url.rstrip('/')}/api/{self.config.airflow_api_version}{path}",
            token=token,
            params=params,
            json=body,
        )

    def pages(self, path: str, key: str, **params: object) -> list[dict]:
        items: list[dict] = []
        for page in range(self.config.max_pages):
            response = self.call("GET", path, params={**params, "limit": 100, "offset": page * 100})
            batch = response.get(key, [])
            items.extend(batch)
            if len(batch) < 100 or len(items) >= response.get("total_entries", float("inf")):
                return items
        raise RuntimeError("Airflow pagination limit exceeded; watermark was not advanced")

    def runs(self, dag: str, since: datetime) -> list[dict]:
        path = f"/dags/{part(dag)}/dagRuns"
        # Both APIs reject ``updated_at_gte`` on DAG-run listing.  Airflow 2
        # exposes execution/start/end dates; Airflow 3 exposes their renamed
        # logical/run-after equivalents.  Read all documented date dimensions
        # and merge by run id so a run that starts before the watermark but
        # finishes after it is still collected.  The collector separately
        # revisits locally queued/running rows, covering runs without dates.
        stamp = since.isoformat()
        filters = (
            ({"execution_date_gte": stamp}, {"start_date_gte": stamp}, {"end_date_gte": stamp})
            if self.config.airflow_api_version == "v1"
            else ({"run_after_gte": stamp}, {"start_date_gte": stamp}, {"end_date_gte": stamp})
        )
        runs = [run for query in filters for run in self.pages(path, "dag_runs", **query)]
        return list({r["dag_run_id"]: r for r in runs}.values())

    def tasks(self, dag: str, run: str) -> list[dict]:
        return self.pages(f"/dags/{part(dag)}/dagRuns/{part(run)}/taskInstances", "task_instances")

    def task_path(self, task: dict) -> str:
        return f"/dags/{part(task['dag_id'])}/dagRuns/{part(task['dag_run_id'])}/taskInstances/{part(task['task_id'])}"

    def job_id(self, task: dict) -> int | None:
        try:
            response = self.call(
                "GET",
                self.task_path(task) + "/xcomEntries/return_value",
                params={"map_index": task.get("map_index", -1)},
            )
        except http.UpstreamError as exc:
            if exc.status == 404:
                return None
            raise
        value = response.get("value")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return None
        if isinstance(value, dict):
            value = value.get("job_id") or value.get("jobId")
        return int(value) if isinstance(value, int | str) and str(value).isdigit() else None

    def log(self, task: dict) -> str:
        response = self.call(
            "GET",
            self.task_path(task) + f"/logs/{max(task.get('try_number') or 1, 1)}",
            params={"map_index": task.get("map_index", -1), "full_content": True},
        )
        content = response.get("content", "")
        return content if isinstance(content, str) else json.dumps(content)

    def retry(self, task: dict) -> dict:
        if task["dag_id"] not in self.config.airflow_dags.values():
            raise ValueError("DAG is outside the configured retry allowlist")
        mapped = task.get("map_index", -1) >= 0
        if mapped and self.config.airflow_api_version == "v1":
            # Airflow 2's clearTaskInstances schema accepts task IDs only, not map indices.
            # Never silently clear every tenant's mapped task.
            raise ValueError(
                "Airflow 2 cannot scope REST clear to one map index. Use Airflow UI for mapped retries, or Airflow 3."
            )
        ids = [[task["task_id"], task["map_index"]]] if mapped else [task["task_id"]]
        return self.call(
            "POST",
            f"/dags/{part(task['dag_id'])}/clearTaskInstances",
            body={
                "dag_run_id": task["dag_run_id"],
                "task_ids": ids,
                "dry_run": False,
                "only_failed": True,
                "reset_dag_runs": True,
                "include_upstream": False,
                "include_downstream": False,
                "include_past": False,
                "include_future": False,
            },
        )

    def trigger_onboarding(self, operation_id: str, conf: dict) -> dict:
        return self.call(
            "POST",
            f"/dags/{part(self.config.onboarding_dag_id)}/dagRuns",
            body={
                "dag_run_id": f"obs__{operation_id}",
                "logical_date": None,
                "conf": conf,
            },
        )

    def dag_run(self, dag_id: str, run_id: str) -> dict:
        return self.call("GET", f"/dags/{part(dag_id)}/dagRuns/{part(run_id)}")

    def trigger_workflow_dag(self, dag_id: str, run_id: str, conf: dict) -> dict:
        if dag_id not in self.config.resolved_onboarding_dags().values():
            raise ValueError("DAG is outside the configured onboarding allowlist")
        return self.call(
            "POST",
            f"/dags/{part(dag_id)}/dagRuns",
            body={"dag_run_id": run_id, "logical_date": None, "conf": conf},
        )

    def health(self) -> dict:
        path = "/monitor/health" if self.config.airflow_api_version == "v2" else "/health"
        return self.call("GET", path)
