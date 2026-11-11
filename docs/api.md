# API reference

The API serves its OpenAPI contract at `/api/openapi.json` and the interactive reference at `/api/docs`.

## Routes

| Method | Path | Operation |
|---|---|---|
| `GET` | `/api/access` | Access |
| `GET` | `/api/alert-rules` | Rules |
| `PUT` | `/api/alert-rules/{id}` | Update Rule |
| `GET` | `/api/alerts` | Alerts |
| `POST` | `/api/alerts/{id}/ack` | Ack |
| `POST` | `/api/alerts/{id}/resolve` | Resolve |
| `GET` | `/api/audit` | Audit |
| `POST` | `/api/auth/change-password` | Change Password |
| `POST` | `/api/auth/forgot-password` | Forgot Password |
| `POST` | `/api/auth/login` | Login |
| `POST` | `/api/auth/logout` | Logout |
| `GET` | `/api/auth/oidc/callback` | Oidc Callback |
| `GET` | `/api/auth/oidc/start` | Oidc Start |
| `POST` | `/api/auth/password` | Change Password |
| `GET` | `/api/channels` | Channels |
| `POST` | `/api/channels/{id}/test` | Test Channel |
| `GET` | `/api/config` | Runtime Config |
| `GET` | `/api/deliveries` | Deliveries |
| `GET` | `/api/dependencies` | Dependencies |
| `GET` | `/api/dependencies/tenants` | Dependency Tenants |
| `GET` | `/api/errors/groups` | Groups |
| `GET` | `/api/errors/groups/{fingerprint}` | Group |
| `GET` | `/api/freshness` | Freshness |
| `GET` | `/api/health` | Health |
| `GET` | `/api/health/live` | Liveness |
| `GET` | `/api/investigation/timeline` | Timeline |
| `GET` | `/api/me` | Me |
| `GET` | `/api/metrics/durations` | Durations |
| `GET` | `/api/metrics/failures-breakdown` | Failures Breakdown |
| `GET` | `/api/metrics/failures-heatmap` | Heatmap |
| `GET` | `/api/metrics/mttr` | Mttr |
| `GET` | `/api/metrics/overview` | Metrics Overview |
| `GET` | `/api/metrics/tenants` | Metrics Tenants |
| `POST` | `/api/onboarding` | Onboard |
| `POST` | `/api/onboarding/preflight` | Preflight |
| `GET` | `/api/onboarding/{tenant_id}` | Onboarding |
| `POST` | `/api/onboarding/{tenant_id}/resume` | Resume Onboarding |
| `GET` | `/api/operations` | Operations |
| `POST` | `/api/operations/{id}/reconcile` | Reconcile |
| `GET` | `/api/overview` | Overview |
| `GET` | `/api/pipelines/catalog` | Catalog |
| `GET` | `/api/platform/health` | Platform |
| `GET` | `/api/quality/checks` | Checks |
| `POST` | `/api/quality/checks` | Create |
| `PATCH` | `/api/quality/checks/{id}` | Toggle |
| `PUT` | `/api/quality/checks/{id}` | Update |
| `POST` | `/api/quality/checks/{id}/run` | Run |
| `GET` | `/api/quality/results` | Results |
| `GET` | `/api/roles` | List Roles |
| `POST` | `/api/roles` | Create Role |
| `DELETE` | `/api/roles/{name}` | Delete Role |
| `GET` | `/api/runs` | Runs |
| `GET` | `/api/runs/{run_key}` | Run Detail |
| `GET` | `/api/runs/{run_key}/log` | Log |
| `POST` | `/api/runs/{run_key}/retry` | Retry |
| `GET` | `/api/saved-views` | Saved Views |
| `POST` | `/api/saved-views` | Save View |
| `DELETE` | `/api/saved-views/{view_id}` | Delete View |
| `GET` | `/api/schema-changes` | Schema |
| `GET` | `/api/search` | Search |
| `GET` | `/api/stream` | Stream |
| `GET` | `/api/tenants` | Tenants |
| `GET` | `/api/tenants/{id}` | Tenant Detail |
| `PATCH` | `/api/tenants/{id}` | Update Tenant |
| `GET` | `/api/tenants/{id}/metrics` | Tenant Metrics |
| `POST` | `/api/tenants/{id}/resync` | Resync |
| `GET` | `/api/tenants/{id}/timeline` | Timeline |
| `POST` | `/api/tenants/{id}/trigger` | Trigger |
| `GET` | `/api/tenants/{id}/workflow` | Workflow |
| `GET` | `/api/users` | Users |
| `POST` | `/api/users` | Create User |
| `DELETE` | `/api/users/{id}` | Delete User |
| `PATCH` | `/api/users/{id}` | Update User |
| `GET` | `/api/users/{id}/permissions` | Get User Permissions |
| `PUT` | `/api/users/{id}/permissions` | Set User Permissions |
| `POST` | `/api/users/{id}/reset-password` | Reset Password |
| `POST` | `/api/users/{id}/revoke-sessions` | Revoke Sessions |
| `GET` | `/api/volume-anomalies` | Volume |
| `GET` | `/api/warehouse` | Warehouse |
