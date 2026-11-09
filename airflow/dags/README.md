# DAG integration review (M6)

No existing team DAG is changed by this M0–M4 implementation. Live onboarding and execution remain disabled. Review the following change in the team's DAG repository when M6 starts.

1. Keep the four configured DAG identifiers (`mysql_initial_load`, `mysql_cdc`, `mongo_initial_load`, `mongo_cdc`) in environment/configuration, replacing placeholders with deployed IDs.
2. Add a runtime `get_active_tenants` task that reads `obs.tenants WHERE status='active'`, then filters by `has_mysql` or `has_mongo`. The task must query at execution time, never during DAG parsing.
3. Dynamically map the existing Airbyte sync task over that task's returned list, with one tenant/connection per mapped instance. With Airflow 2.9+, use `map_index_template` to render the tenant slug.
4. Leave the Airbyte job ID in XCom `return_value` and retain `map_index`, allowing the collector to link the task and job without double counting. The connection ID is the primary tenant mapping key.
5. A newly active or resumed tenant is then included on the next scheduled DAG run. Paused and offboarded tenants are excluded.
6. Review a separate `onboard_tenant` DAG implementing create/check sources → create connections → save IDs → run initial loads → activate. Write each step to `obs.tenant_events` and emit NOTIFY events. It must receive secret references only, resolve them inside trusted service code, redact failures, and be restart-safe.

Validate against recorded APIs first, then a staging tenant. Airflow 2.x `/api/v1` and Airflow 3.x `/api/v2` use different authentication and contracts; do not infer compatibility. The console API's write identity must be restricted to the four DAGs and the onboarding DAG. Review this with the data team before applying changes.
