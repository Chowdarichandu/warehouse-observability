# Integration contract fixtures

These synthetic, sanitized fixtures exercise the published Airflow 2.10/3.1 and Airbyte API shapes. They were **not recorded from staging**. Tests replay them with HTTP MockTransport and botocore Stubber; no real Airflow, Airbyte, AWS, warehouse, or notification endpoints are contacted.

Before release, capture sanitized responses from the actual deployed versions and compare 20 sampled runs with the Airflow UI, including mapped tasks, retries, failures, late task updates, and externally triggered Airbyte jobs. Track that evidence in the staging acceptance report. Keep credentials and tenant data out of fixtures.

## Coverage

| Fixture | Contract |
|---|---|
| `airflow-v1-dag-runs.json`, `airflow-v2-dag-runs.json` | DAG run listing for Airflow 2.x (`/api/v1`) and 3.x (`/api/v2`), including the version-specific watermark filter fields |
| `airflow-v1-task-instances.json`, `airflow-v2-task-instances.json` | Task instance listing, including a mapped task with `rendered_map_index` |
| `airflow-xcom-return-value.json` | XCom `return_value` carrying the linked Airbyte job id |
| `airflow-v1-health.json`, `airflow-v2-health.json` | `/health` (2.x) and `/monitor/health` (3.x) |
| `airflow-pools.json` | Pool listing used by the platform checks |
| `airflow-import-errors.json` | DAG import error listing |
| `airbyte-jobs-list.json` | Public API job listing (`data` envelope, ISO-8601 durations) |
| `airbyte-job.json` | Public API job detail with merged attempt diagnostics |
| `airbyte-config-job.json` | Config API `jobs/get` attempts, failure summary and stream stats |
| `airflow-task.json` | Single task instance used by the linker and ingest tests |

`tests/backend/test_contract_fixtures.py` replays each fixture through the
clients; `tests/backend/test_live_integrations.py` covers the ingest path.
