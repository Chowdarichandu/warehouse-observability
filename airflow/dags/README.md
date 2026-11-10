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

## Seven-DAG onboarding

The reference templates define one coordinator, one provisioning DAG per source, and MySQL/MongoDB initial-load and CDC DAGs. Configure the coordinator with `ONBOARDING_DAG_ID`, the four sync DAGs with `AIRFLOW_DAGS`, and optional per-node overrides with `ONBOARDING_DAG_IDS`. Use seven distinct IDs. The coordinator triggers each enabled branch in order: provisioning, initial load, then first CDC. Each attempt has a persisted deterministic run ID and status. The coordinator sensor uses reschedule mode to release its worker slot while it waits.

The offline demo simulates these steps and never contacts external systems. **Live onboarding and resume are disabled** until the connector's shared MongoDB `tenant_id` isolation and the recovery of uncertain writes, sensor timeouts, and partially completed coordinator runs have been tested and corrected in staging. Do not deploy the reference DAGs against live sources until those checks pass. MySQL uses tenant-specific databases; MongoDB documents share a cluster and must be isolated by the confirmed `tenant_id` mapping. The field's exact value mapping and Airbyte connector filtering behavior require confirmation; naming a field in the UI does not enforce isolation.

Resolve `airflow/worker-requirements.in` against the deployed Airflow constraints, install the reviewed console wheel with `--no-deps`, and configure workers with `SERVICE_KIND=airflow_worker`, `MODE=live`, TLS database access, reviewed DAG mappings, scoped Airbyte/AWS credentials, and the required action flags. Workers do not require the console's JWT or OIDC client secret. The API must run as `SERVICE_KIND=console` and retains its stricter authentication validation. Do not install the API dependency lock into Airflow. Configure Airflow and Airbyte credentials through approved secret backends.

DAG `conf` carries only workflow, tenant, node and attempt references. Secrets remain in the approved secrets backend; a worker retrieves the persisted onboarding request after validating its run binding. The seven-DAG templates were imported in an isolated Airflow 2.11 environment with an Airbyte provider; this does not establish compatibility with the deployed versions or prove a live run.

## References

- [Airflow 2 REST API](https://airflow.apache.org/docs/apache-airflow/2.10.5/stable-rest-api-ref.html)
- [Airflow 3 REST API](https://airflow.apache.org/docs/apache-airflow/3.1.3/stable-rest-api-ref.html)
- [Airbyte provider operators](https://airflow.apache.org/docs/apache-airflow-providers-airbyte/stable/operators/airbyte.html)
- [AWS MWAA REST API access](https://docs.aws.amazon.com/mwaa/latest/userguide/access-mwaa-apache-airflow-rest-api.html)
