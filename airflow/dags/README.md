# Airflow integration and DAG migration

`templates/registry_pipelines.py` and `templates/onboard_tenant.py` are new reference DAGs. They do not modify the team's existing DAGs. Review and test them in the actual Airflow repo before deployment.

## Versions and authentication

The collector supports the Airflow 2 REST `/api/v1` and Airflow 3 REST `/api/v2` contracts, selected by `AIRFLOW_API_VERSION`. Self-hosted EC2/EKS Airflow needs a read-only Viewer bearer credential and a separate restricted operator credential (via the installed auth manager or token-auth gateway). Default Airflow 2 BasicAuth does not accept bearer tokens; configure the transport/authentication before release. For MWAA use `AIRFLOW_TRANSPORT=mwaa`, `MWAA_ENVIRONMENT`, an IAM Viewer role, and optional `MWAA_WRITE_ROLE_ARN` for mutations. Test actual MWAA endpoint and log limits with the deployed version.

The templates use Airflow 2.9+ or Airflow 3, a compatible pinned `apache-airflow-providers-airbyte`, and the Airbyte provider's `airbyte_operations` connection. Resolve it through the Airflow AWS Secrets Manager backend; never put connector passwords in DAG files or Variables. Configure `airbyte_sync` and `airbyte_wait` pools for the desired concurrency. Sensor reschedule mode frees worker slots. Operator retries are zero because an ambiguous failed trigger must be reconciled before another write.

## Migration sequence

1. Create an observation-store login with the `obs_ro` group role and set a secret-backed `OBS_DATABASE_URL` for Airflow. Install `psycopg[binary]` on workers. Every DSN must verify TLS hostnames.
2. Copy the template DAG files into a **staging** DAG repository. The `obs_` prefix avoids replacing existing DAG IDs. DAG parsing performs no database query or API call; tenant registration is read inside `get_active_tenants` at task runtime.
3. Populate tenant connection mappings through `python -m obs.configure` and set `AIRFLOW_DAGS` to the deployed IDs. Set `SYNC_TASK_REGEX=^sync$` for these templates. Connection IDs resolve mapped tenants, so task-name parsing is unnecessary.
4. Validate that MySQL/Mongo CDC connections use manually scheduled Airbyte syncs; otherwise both Airbyte and Airflow may independently schedule the same pipeline. Initial-load DAGs have no hourly schedule. Review stream sync modes and destination overwrite/deduplication behavior before initial loads.
5. Run one staging tenant through each enabled pipeline. The async trigger stores the Airbyte job ID in XCom. A separate rescheduling sensor waits for completion. The collector follows linked Airbyte status even after the trigger task succeeds, and revisits unfinished jobs outside the watermark window.
6. Compare 20 staging runs, including map indices, queue delays, XCom fallback, retries, failed sensors, logs, and standalone jobs. Map every existing connection exactly once. Unresolved tasks remain visible under `_unmapped`.
7. Pause the team's old schedule and enable the new CDC schedule in an approved change window. Never run both hourly schedules. Only after confirming the runtime registry works should `REGISTRY_DAGS_ENABLED=true` and then `LIVE_ACTIONS_ENABLED=true` be set.

Pause/resume updates tenant registry status; it does not pause an entire shared DAG and does not cancel already running tasks. The next runtime registry query applies the new status. A resume includes that tenant on the next CDC schedule without a DAG deployment.

## Retry isolation

Airflow 3 supports clearing one `[task_id, map_index]`; the client supplies only that DAG run and disables upstream/downstream/past/future expansion. Airflow 2's public `clearTaskInstances` body cannot safely isolate a single mapped index, so the console rejects that mapped retry and directs the operator to Airflow. Unmapped failed tasks remain retryable. For async Airbyte trigger tasks that already succeeded but whose Airbyte job failed, the API starts a new sync on the same connection instead of clearing a successful trigger.

## Onboarding

Install the repository's `obs-console` wheel with `--no-deps` on every onboarding worker, and resolve `airflow/worker-requirements.in` against the **deployed Airflow constraints file**. Do not install the API service lock into Airflow: it includes FastAPI/Starlette pins that may conflict with the Airflow webserver. Pin and test the resulting worker environment before deployment. Configure that worker with `MODE=live`, the required live/OIDC validation settings, an observation-store `obs_app` login, scoped AWS secret access, a restricted Airbyte write credential, `AIRBYTE_WORKSPACE_ID`, `AIRBYTE_DESTINATION_ID`, and **OSS** `AIRBYTE_CONFIG_URL` for source connection checks. The current provisioning workflow uses the OSS check endpoint; validate/extend that step before using Airbyte Cloud. The destination schema must already exist with approved grants.

The console accepts only secret references. `aws://observability/tenants/<tenant>/mysql` resolves a JSON secret containing `password`, a reviewed connector-specific `airbyte_configuration`, and explicit `initial_streams`/`cdc_streams` public API stream configurations. The Mongo secret includes `uri` and the same reviewed Airbyte fields. Ensure those connector configurations reference exactly the hosts/databases validated by preflight. Connector schemas vary by version; use the deployed connector's exported configuration, never guess a CDC schema or stream cursor. Restrict `AWS_SECRET_PREFIX` and `SOURCE_ALLOWED_CIDRS` to the approved tenant namespace/network.

`onboard_tenant` receives the wizard fields and references as `dag_run.conf`. The worker records each source/connection/job ID in `obs.provisioning_resources` before advancing, checks sources through Airbyte, creates manual initial and CDC connections with the tenant warehouse namespace, waits for every requested initial job to succeed, then activates the tenant. Failed steps remain visible in tenant events. It never marks a failed or timed-out initial load healthy.

A resource in `creating` or `uncertain` is never automatically created again. Inspect Airbyte, reconcile its actual ID in the registry using a controlled database maintenance session, record an audit entry, then rerun the failed DAG task. Never delete a resource marker until absence is confirmed upstream. API operations can be reconciled through Administration with evidence before a new request. DAG runs have deterministic `obs__<operation-id>` IDs; existing IDs prevent duplicate Airflow triggers.

## References

- [Airflow 2 REST API](https://airflow.apache.org/docs/apache-airflow/2.10.5/stable-rest-api-ref.html)
- [Airflow 3 REST API](https://airflow.apache.org/docs/apache-airflow/3.1.3/stable-rest-api-ref.html)
- [Airbyte provider operators](https://airflow.apache.org/docs/apache-airflow-providers-airbyte/stable/operators/airbyte.html)
- [AWS MWAA REST API access](https://docs.aws.amazon.com/mwaa/latest/userguide/access-mwaa-apache-airflow-rest-api.html)
