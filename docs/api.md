# API reference

The API serves its OpenAPI contract at `/api/v1/openapi.json` and the interactive reference at `/api/v1/docs`.

## Routes

| Method | Path | Operation |
|---|---|---|
| `GET` | `/api/v1/access` | Access |
| `DELETE` | `/api/v1/access/roles/{role_name}/modules/{module_id}` | Revoke Role Module |
| `PUT` | `/api/v1/access/roles/{role_name}/modules/{module_id}` | Grant Role Module |
| `PUT` | `/api/v1/access/users/{id}/modules/{module_id}` | Set User Module |
| `GET` | `/api/v1/alert-rules` | Rules |
| `PUT` | `/api/v1/alert-rules/{id}` | Update Rule |
| `GET` | `/api/v1/alerts` | Alerts |
| `POST` | `/api/v1/alerts/{id}/ack` | Ack |
| `POST` | `/api/v1/alerts/{id}/resolve` | Resolve |
| `GET` | `/api/v1/audit` | Audit |
| `POST` | `/api/v1/auth/change-password` | Change Password |
| `POST` | `/api/v1/auth/forgot-password` | Forgot Password |
| `POST` | `/api/v1/auth/login` | Login |
| `POST` | `/api/v1/auth/logout` | Logout |
| `GET` | `/api/v1/auth/oidc/callback` | Oidc Callback |
| `GET` | `/api/v1/auth/oidc/start` | Oidc Start |
| `POST` | `/api/v1/auth/password` | Change Password |
| `GET` | `/api/v1/channels` | Channels |
| `POST` | `/api/v1/channels/{id}/test` | Test Channel |
| `GET` | `/api/v1/config` | Runtime Config |
| `GET` | `/api/v1/deliveries` | Deliveries |
| `GET` | `/api/v1/dependencies` | Dependencies |
| `GET` | `/api/v1/dependencies/tenants` | Dependency Tenants |
| `GET` | `/api/v1/dev/mailbox` | Dev Mailbox |
| `GET` | `/api/v1/errors/groups` | Groups |
| `GET` | `/api/v1/errors/groups/{fingerprint}` | Group |
| `GET` | `/api/v1/forecast` | Forecast |
| `GET` | `/api/v1/freshness` | Freshness |
| `GET` | `/api/v1/health` | Health |
| `GET` | `/api/v1/health/live` | Liveness |
| `GET` | `/api/v1/incidents` | Incidents |
| `GET` | `/api/v1/incidents/{incident_id}` | Incident |
| `POST` | `/api/v1/incidents/{incident_id}/ack` | Acknowledge |
| `POST` | `/api/v1/incidents/{incident_id}/assign` | Assign |
| `POST` | `/api/v1/incidents/{incident_id}/notes` | Note |
| `POST` | `/api/v1/incidents/{incident_id}/resolve` | Resolve |
| `GET` | `/api/v1/investigation/timeline` | Timeline |
| `GET` | `/api/v1/me` | Me |
| `GET` | `/api/v1/metrics/durations` | Durations |
| `GET` | `/api/v1/metrics/failures-breakdown` | Failures Breakdown |
| `GET` | `/api/v1/metrics/failures-heatmap` | Heatmap |
| `GET` | `/api/v1/metrics/mttr` | Mttr |
| `GET` | `/api/v1/metrics/overview` | Metrics Overview |
| `GET` | `/api/v1/metrics/tenants` | Metrics Tenants |
| `POST` | `/api/v1/onboarding` | Onboard |
| `POST` | `/api/v1/onboarding/preflight` | Preflight |
| `GET` | `/api/v1/onboarding/{tenant_id}` | Onboarding |
| `POST` | `/api/v1/onboarding/{tenant_id}/resume` | Resume Onboarding |
| `GET` | `/api/v1/operations` | Operations |
| `POST` | `/api/v1/operations/{id}/reconcile` | Reconcile |
| `GET` | `/api/v1/overview` | Overview |
| `GET` | `/api/v1/pipelines/catalog` | Catalog |
| `GET` | `/api/v1/platform/health` | Platform |
| `GET` | `/api/v1/quality/checks` | Checks |
| `POST` | `/api/v1/quality/checks` | Create |
| `PATCH` | `/api/v1/quality/checks/{id}` | Toggle |
| `PUT` | `/api/v1/quality/checks/{id}` | Update |
| `POST` | `/api/v1/quality/checks/{id}/run` | Run |
| `GET` | `/api/v1/quality/results` | Results |
| `GET` | `/api/v1/roles` | List Roles |
| `POST` | `/api/v1/roles` | Create Role |
| `DELETE` | `/api/v1/roles/{name}` | Delete Role |
| `GET` | `/api/v1/runs` | Runs |
| `GET` | `/api/v1/runs/{run_key}` | Run Detail |
| `GET` | `/api/v1/runs/{run_key}/log` | Log |
| `POST` | `/api/v1/runs/{run_key}/retry` | Retry |
| `GET` | `/api/v1/saved-views` | Saved Views |
| `POST` | `/api/v1/saved-views` | Save View |
| `DELETE` | `/api/v1/saved-views/{view_id}` | Delete View |
| `GET` | `/api/v1/schema-changes` | Schema |
| `GET` | `/api/v1/search` | Search |
| `GET` | `/api/v1/stream` | Stream |
| `GET` | `/api/v1/tenants` | Tenants |
| `GET` | `/api/v1/tenants/{id}` | Tenant Detail |
| `PATCH` | `/api/v1/tenants/{id}` | Update Tenant |
| `GET` | `/api/v1/tenants/{id}/maintenance-windows` | Maintenance Windows |
| `POST` | `/api/v1/tenants/{id}/maintenance-windows` | Create Maintenance Window |
| `DELETE` | `/api/v1/tenants/{id}/maintenance-windows/{window_id}` | Delete Maintenance Window |
| `GET` | `/api/v1/tenants/{id}/metrics` | Tenant Metrics |
| `POST` | `/api/v1/tenants/{id}/resync` | Resync |
| `GET` | `/api/v1/tenants/{id}/timeline` | Timeline |
| `POST` | `/api/v1/tenants/{id}/trigger` | Trigger |
| `GET` | `/api/v1/tenants/{id}/workflow` | Workflow |
| `GET` | `/api/v1/users` | Users |
| `POST` | `/api/v1/users` | Create User |
| `DELETE` | `/api/v1/users/{id}` | Delete User |
| `PATCH` | `/api/v1/users/{id}` | Update User |
| `GET` | `/api/v1/users/{id}/permissions` | Get User Permissions |
| `PUT` | `/api/v1/users/{id}/permissions` | Set User Permissions |
| `POST` | `/api/v1/users/{id}/reset-password` | Reset Password |
| `POST` | `/api/v1/users/{id}/revoke-sessions` | Revoke Sessions |
| `GET` | `/api/v1/volume-anomalies` | Volume |
| `GET` | `/api/v1/warehouse` | Warehouse |
