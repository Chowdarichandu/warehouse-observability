# Configuration

Every application setting is listed below. Live integrations never run in demo mode. Secrets belong in the service-specific Secrets Manager JSON, not Git. JSON arrays/maps must be encoded on a single line.

- `MODE`: typing.Literal['demo', 'live']. Default: `demo`.
- `DEMO_PUBLIC`: <class 'bool'>. Default: `False`. Enables the hosted, read-only demo flow; it cannot be used with `MODE=live`.
- `ALLOW_LOCAL_AUTH_IN_LIVE`: <class 'bool'>. Default: `False`. Allows local password authentication in live mode when explicitly enabled.
- `DATABASE_URL`: <class 'str'>. Default: `postgresql://obs:obs_local@127.0.0.1:55432/obs`.
- `JWT_SECRET`: <class 'str'>. Default: `local-demo-only-change-before-live-use-32-characters`.
- `DEMO_PASSWORD`: <class 'str'>. Default: `demo`.
- `COOKIE_SECURE`: <class 'bool'>. Default: `True`.
- `POLL_INTERVAL_SEC`: <class 'int'>. Default: `120`.
- `PLATFORM_CHECK_SEC`: <class 'int'>. Default: `60`.
- `WAREHOUSE_CHECK_SEC`: <class 'int'>. Default: `900`.
- `DEMO_TICK_SEC`: <class 'float'>. Default: `60`.
- `DEMO_RETRY_SEC`: <class 'float'>. Default: `30`.
- `DEMO_ONBOARD_STEP_SEC`: <class 'float'>. Default: `10`.
- `ALERT_INTERVAL_SEC`: <class 'float'>. Default: `60`.
- `CONSOLE_URL`: <class 'str'>. Default: `http://localhost:8080`.
- `ENVIRONMENT_NAME`: <class 'str'>. Default: `Production`.
- `LIVE_ACTIONS_ENABLED`: <class 'bool'>. Default: `False`.
- `HTTP_TIMEOUT_SEC`: <class 'int'>. Default: `20`.
- `MAX_PAGES`: <class 'int'>. Default: `100`.
- `AWS_REGION`: <class 'str'>. Default: `us-east-1`.
- `AWS_SECRET_PREFIX`: <class 'str'>. Default: `observability/`.
- `AIRFLOW_TRANSPORT`: typing.Literal['http', 'mwaa']. Default: `http`.
- `AIRFLOW_API_VERSION`: typing.Literal['v1', 'v2']. Default: `v1`.
- `AIRFLOW_URL`: <class 'str'>. Default: ``.
- `AIRFLOW_READ_TOKEN`: <class 'str'>. Default: ``.
- `AIRFLOW_WRITE_TOKEN`: <class 'str'>. Default: ``.
- `MWAA_ENVIRONMENT`: <class 'str'>. Default: ``.
- `MWAA_WRITE_ROLE_ARN`: <class 'str'>. Default: ``.
- `AIRFLOW_DAGS`: dict[str, str]. Default: `{'mysql_initial': 'mysql_initial_load', 'mysql_cdc': 'mysql_cdc', 'mongo_initial': 'mongo_initial_load', 'mongo_cdc': 'mongo_cdc'}`.
- `SYNC_TASK_REGEX`: <class 'str'>. Default: `(^|\.)sync(_.*)?$`.
- `TENANT_TASK_REGEX`: <class 'str'>. Default: `^sync_(?P<tenant>[a-z0-9_]+)$`.
- `ONBOARDING_DAG_ID`: <class 'str'>. Default: `onboard_tenant`.
- `REGISTRY_DAGS_ENABLED`: <class 'bool'>. Default: `False`.
- `AIRBYTE_URL`: <class 'str'>. Default: ``.
- `AIRBYTE_TOKEN`: <class 'str'>. Default: ``.
- `AIRBYTE_WRITE_TOKEN`: <class 'str'>. Default: ``.
- `AIRBYTE_CLIENT_ID`: <class 'str'>. Default: ``.
- `AIRBYTE_CLIENT_SECRET`: <class 'str'>. Default: ``.
- `AIRBYTE_CONFIG_URL`: <class 'str'>. Default: ``.
- `AIRBYTE_WORKSPACE_ID`: <class 'str'>. Default: ``.
- `AIRBYTE_DESTINATION_ID`: <class 'str'>. Default: ``.
- `WAREHOUSE_ENGINE`: typing.Literal['postgres', 'redshift']. Default: `postgres`.
- `WAREHOUSE_URL`: <class 'str'>. Default: ``.
- `WAREHOUSE_LOAD_COLUMN`: <class 'str'>. Default: `_airbyte_extracted_at`.
- `WAREHOUSE_STATEMENT_TIMEOUT_MS`: <class 'int'>. Default: `10000`.
- `SOURCE_ALLOWED_CIDRS`: list[str]. Default: `[]`.
- `MYSQL_BINLOG_RETENTION_SEC`: <class 'int'>. Default: `259200`.
- `SOURCE_CA_FILE`: <class 'str'>. Default: ``.
- `AUTH_PROVIDER`: typing.Literal['local', 'oidc']. Default: `local`.
- `OIDC_ISSUER`: <class 'str'>. Default: ``.
- `OIDC_CLIENT_ID`: <class 'str'>. Default: ``.
- `OIDC_CLIENT_SECRET`: <class 'str'>. Default: ``.
- `OIDC_GROUPS_CLAIM`: <class 'str'>. Default: `groups`.
- `OIDC_GROUP_ROLES`: dict[str, typing.Literal['viewer', 'operator', 'admin']]. Default: `{}`.
- `SESSION_HOURS`: <class 'int'>. Default: `8`.
- `NOTIFICATION_MAX_ATTEMPTS`: <class 'int'>. Default: `5`.
- `NOTIFICATION_ALLOWED_HOSTS`: list[str]. Default: `['hooks.slack.com', 'outlook.office.com']`.
- `SES_FROM_ADDRESS`: <class 'str'>. Default: ``.
- `SES_TO_ADDRESSES`: list[str]. Default: `[]`.
- `SNS_TOPIC_ARN`: <class 'str'>. Default: ``.
- `RETENTION_ENABLED`: <class 'bool'>. Default: `True`.
- `BACKUP_S3_BUCKET`: <class 'str'>. Default: ``.
- `BACKUP_KMS_KEY_ID`: <class 'str'>. Default: ``.

`OBS_CONFIG_SECRET_ID` selects a per-service Secrets Manager JSON for the entrypoint; `AWS_REGION` selects its region. `SLACK_WEBHOOK_URL`, `TEAMS_WEBHOOK_URL`, and `SMTP_URL` are channel target environment variables. `OBS_DB_PASSWORD` is only for the local Compose database. `OBS_DATABASE_URL` is the read-only Airflow registry DSN. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` and `OBS_NATIVE` are developer-only settings.

The native demo runner supports isolated local workspaces through `OBS_RUNTIME_DIR` (a dedicated directory directly under `/tmp` named `obs-console-*`), `OBS_PG_PORT` (default 55432) and `OBS_API_PORT` (default 8000). `OBS_WEB_PORT` optionally changes the web port (default 8080); CI uses 18080 for container checks. `OBS_API_PROXY_TARGET` changes the API target for a local Vite dev server when it needs to run beside another console instance.

## Data-quality scheduler

`QUALITY_ENABLED=false` disables warehouse quality execution in live mode until explicitly reviewed. Demo checks use only synthetic local evidence. `QUALITY_INTERVAL_SEC=60` sets the scheduler polling interval (minimum 60 seconds); each check has its own interval, default 900 seconds, minimum 60. Checks read only their tenant's registered warehouse schema, at most 10,000 rows, with a statement timeout capped at 10 seconds. See [quality](quality.md).

Release tools use separate invocation-only variables: `OBS_LOAD_SESSION` is an authenticated staging viewer session (never a CLI argument); `OBS_DRILL_ADMIN_DSN` identifies a dedicated loopback PostgreSQL server permitted to create scratch databases. These are not application service settings. See [release safeguards](release-safeguards.md).

`SERVICE_KIND=console` is required for the API. Reviewed Airflow workers use `SERVICE_KIND=airflow_worker`; the API refuses to start in worker mode. `ONBOARDING_DAG_IDS` optionally overrides individual DAG IDs; defaults retain `ONBOARDING_DAG_ID` and `AIRFLOW_DAGS`.

The onboarding registry must resolve to seven distinct DAG IDs: the coordinator, MySQL provisioning, Mongo provisioning, MySQL initial load, MySQL CDC, Mongo initial load, and Mongo CDC. Analytics DAGs are observed after the source load and are not part of the operator trigger allowlist. Keep the mapping in the service secret or reviewed configuration and verify it with `python -m obs.configure <path> --check` before enabling registry actions.


`DEMO_UNSAFE_SELF_SERVICE_PASSWORD_RESET` defaults to `false`. The optional legacy self-service reset exposes temporary passwords and must only be enabled in a disposable, isolated demo; it is never enabled in live mode.
