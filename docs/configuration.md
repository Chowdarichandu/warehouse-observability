# Configuration

Every application setting is listed below. Live integrations never run in demo mode. Secrets belong in the service-specific Secrets Manager JSON, not Git. JSON arrays/maps must be encoded on a single line.

<!-- BEGIN GENERATED SETTINGS -->

- `MODE`: one of: demo, live. Default: `demo`.
- `DEMO_PUBLIC`: boolean. Default: `false`.
- `ALLOW_LOCAL_AUTH_IN_LIVE`: boolean. Default: `false`.
- `SERVICE_KIND`: one of: console, airflow_worker. Default: `console`.
- `DATABASE_URL`: string. Default: `postgresql://obs:obs_local@127.0.0.1:55432/obs`.
- `JWT_SECRET`: string. Default: set per environment.
- `DEMO_PASSWORD`: string. Default: set per environment.
- `DEMO_UNSAFE_SELF_SERVICE_PASSWORD_RESET`: boolean. Default: `false`.
- `COOKIE_SECURE`: boolean. Default: `true`.
- `POLL_INTERVAL_SEC`: integer. Default: `120`.
- `PLATFORM_CHECK_SEC`: integer. Default: `60`.
- `WAREHOUSE_CHECK_SEC`: integer. Default: `900`.
- `DEMO_TICK_SEC`: number. Default: `60`.
- `DEMO_RETRY_SEC`: number. Default: `30`.
- `DEMO_ONBOARD_STEP_SEC`: number. Default: `4`.
- `ALERT_INTERVAL_SEC`: number. Default: `60`.
- `CONSOLE_URL`: string. Default: `http://localhost:8080`.
- `ENVIRONMENT_NAME`: string. Default: `Production`.
- `LIVE_ACTIONS_ENABLED`: boolean. Default: `false`.
- `HTTP_TIMEOUT_SEC`: integer. Default: `20`.
- `MAX_PAGES`: integer. Default: `100`.
- `AWS_REGION`: string. Default: `us-east-1`.
- `AWS_SECRET_PREFIX`: string. Default: `observability/`.
- `AIRFLOW_TRANSPORT`: one of: http, mwaa. Default: `http`.
- `AIRFLOW_API_VERSION`: one of: v1, v2. Default: `v1`.
- `AIRFLOW_URL`: string. Default: ``.
- `AIRFLOW_READ_TOKEN`: string. Default: set per environment.
- `AIRFLOW_WRITE_TOKEN`: string. Default: set per environment.
- `MWAA_ENVIRONMENT`: string. Default: ``.
- `MWAA_WRITE_ROLE_ARN`: string. Default: ``.
- `AIRFLOW_DAGS`: object with string values. Default: `{"mongo_cdc":"mongo_cdc","mongo_initial":"mongo_initial_load","mysql_cdc":"mysql_cdc","mysql_initial":"mysql_initial_load"}`.
- `SYNC_TASK_REGEX`: string. Default: `(^|\.)sync(_.*)?$`.
- `TENANT_TASK_REGEX`: string. Default: `^sync_(?P<tenant>[a-z0-9_]+)$`.
- `ONBOARDING_DAG_ID`: string. Default: `onboard_tenant`.
- `ONBOARDING_DAG_IDS`: object with string values. Default: `{}`.
- `REGISTRY_DAGS_ENABLED`: boolean. Default: `false`.
- `AIRBYTE_URL`: string. Default: ``.
- `AIRBYTE_TOKEN`: string. Default: set per environment.
- `AIRBYTE_WRITE_TOKEN`: string. Default: set per environment.
- `AIRBYTE_CLIENT_ID`: string. Default: ``.
- `AIRBYTE_CLIENT_SECRET`: string. Default: set per environment.
- `AIRBYTE_CONFIG_URL`: string. Default: ``.
- `AIRBYTE_WORKSPACE_ID`: string. Default: ``.
- `AIRBYTE_DESTINATION_ID`: string. Default: ``.
- `WAREHOUSE_ENGINE`: one of: postgres, redshift. Default: `postgres`.
- `WAREHOUSE_URL`: string. Default: ``.
- `WAREHOUSE_LOAD_COLUMN`: string. Default: `_airbyte_extracted_at`.
- `WAREHOUSE_STATEMENT_TIMEOUT_MS`: integer. Default: `10000`.
- `QUALITY_ENABLED`: boolean. Default: `false`.
- `QUALITY_INTERVAL_SEC`: integer. Default: `60`.
- `SOURCE_ALLOWED_CIDRS`: array of string. Default: `[]`.
- `MYSQL_BINLOG_RETENTION_SEC`: integer. Default: `259200`.
- `SOURCE_CA_FILE`: string. Default: ``.
- `AUTH_PROVIDER`: one of: local, oidc. Default: `local`.
- `OIDC_ISSUER`: string. Default: ``.
- `OIDC_CLIENT_ID`: string. Default: ``.
- `OIDC_CLIENT_SECRET`: string. Default: set per environment.
- `OIDC_GROUPS_CLAIM`: string. Default: `groups`.
- `OIDC_GROUP_ROLES`: object with one of: viewer, operator, admin values. Default: `{}`.
- `SESSION_IDLE_HOURS`: integer. Default: `12`.
- `SESSION_ABSOLUTE_DAYS`: integer. Default: `7`.
- `NOTIFICATION_MAX_ATTEMPTS`: integer. Default: `5`.
- `NOTIFICATION_ALLOWED_HOSTS`: array of string. Default: `["hooks.slack.com","outlook.office.com"]`.
- `SES_FROM_ADDRESS`: string. Default: ``.
- `SES_TO_ADDRESSES`: array of string. Default: `[]`.
- `SNS_TOPIC_ARN`: string. Default: ``.
- `RETENTION_ENABLED`: boolean. Default: `true`.
- `BACKUP_S3_BUCKET`: string. Default: ``.
- `BACKUP_KMS_KEY_ID`: string. Default: ``.

<!-- END GENERATED SETTINGS -->

`OBS_CONFIG_SECRET_ID` selects a per-service Secrets Manager JSON for the entrypoint; `AWS_REGION` selects its region. `SLACK_WEBHOOK_URL`, `TEAMS_WEBHOOK_URL`, and `SMTP_URL` are channel target environment variables. `OBS_DB_PASSWORD` is only for the local Compose database. `OBS_DATABASE_URL` is the read-only Airflow registry DSN. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` and `OBS_NATIVE` are developer-only settings.

The native demo runner supports isolated local workspaces through `OBS_RUNTIME_DIR` (a dedicated directory directly under `/tmp` named `obs-console-*`), `OBS_PG_PORT` (default 55432) and `OBS_API_PORT` (default 8000). `OBS_WEB_PORT` optionally changes the web port (default 8080); CI uses 18080 for container checks. `OBS_API_PROXY_TARGET` changes the API target for a local Vite dev server when it needs to run beside another console instance.

## Data-quality scheduler

`QUALITY_ENABLED=false` disables warehouse quality execution in live mode until explicitly reviewed. Demo checks use only synthetic local evidence. `QUALITY_INTERVAL_SEC=60` sets the scheduler polling interval (minimum 60 seconds); each check has its own interval, default 900 seconds, minimum 60. Checks read only their tenant's registered warehouse schema, at most 10,000 rows, with a statement timeout capped at 10 seconds. See [quality](quality.md).

Release tools use separate invocation-only variables: `OBS_LOAD_SESSION` is an authenticated staging viewer session (never a CLI argument); `OBS_DRILL_ADMIN_DSN` identifies a dedicated loopback PostgreSQL server permitted to create scratch databases. These are not application service settings. See [release safeguards](release-safeguards.md).

`SERVICE_KIND=console` is required for the API. Reviewed Airflow workers use `SERVICE_KIND=airflow_worker`; the API refuses to start in worker mode. `ONBOARDING_DAG_IDS` optionally overrides individual DAG IDs; defaults retain `ONBOARDING_DAG_ID` and `AIRFLOW_DAGS`.

The onboarding registry must resolve to seven distinct DAG IDs: the coordinator, MySQL provisioning, Mongo provisioning, MySQL initial load, MySQL CDC, Mongo initial load, and Mongo CDC. Analytics DAGs are observed after the source load and are not part of the operator trigger allowlist. Keep the mapping in the service secret or reviewed configuration and verify it with `python -m obs.configure <path> --check` before enabling registry actions. Live onboarding stays off until the tenant isolation check passes and an admin enables live actions for the environment.


`DEMO_UNSAFE_SELF_SERVICE_PASSWORD_RESET` defaults to `false`. The optional legacy self-service reset exposes temporary passwords and must only be enabled in a disposable, isolated demo; it is never enabled in live mode.
