# Data quality

The console supports four built-in checks: null rate, duplicate keys, accepted values, and schema contracts. Administrators create/edit/enable checks; operators can request an evaluation; viewers can inspect aggregate evidence. All mutations check roles/CSRF and write audit records. Live changes additionally require `LIVE_ACTIONS_ENABLED=true`.

Each check belongs permanently to one registered tenant. The schema comes from that tenant's `warehouse_schema`; API clients cannot supply a schema, URL or SQL. Table and column identifiers are validated and quoted. Use dedicated warehouse credentials that grant only catalog access and SELECT on approved tenant tables.

Enable live reads explicitly with `QUALITY_ENABLED=true`. The collector examines due checks every `QUALITY_INTERVAL_SEC` seconds (default 60; 60–3600 allowed). Each check has its own evaluation interval (default 900 seconds; 60–86400 allowed). Paused/offboarded tenants and disabled checks are skipped. Row locks prevent manual/scheduled overlap, a failed check does not stop the next check, and definition/registry failures are recorded under `collector_state` as `quality:<id>`.

Sample checks read at most `sample_limit` rows (default 1000, maximum 10000). Queries run in a read-only transaction with a server-side timeout capped at 10 seconds; identifiers and sample bounds are not interpolated from arbitrary SQL. No full-table count or sort is performed. This limits the rows returned and evaluation memory, while warehouse scan cost still depends on table layout and execution plans. Use an approved low-cost replica/workload queue and validate costs in staging. The sample is an unordered bounded prefix, not a statistically representative random sample and not proof of full-table correctness.

- Null rate is sampled nulls divided by sampled rows.
- Duplicate rate counts rows beyond the first occurrence of each sampled composite key, divided by sampled rows. Null key components participate in comparison. This cannot establish uniqueness outside the sample.
- Accepted values compares each non-null value's string representation against an explicit set (up to 100 entries). Null values are violations. Use a null-rate check when nulls need a separate policy.
- Schema contracts compare `information_schema.columns.data_type` names, case-insensitively, and optionally reject extra columns. Precision, scale and length are not inferred from these type names. Catalogs above 1000 visible columns produce an error rather than a partial pass.

A zero-row sample or unavailable column/catalog returns `error`, rather than declaring a pass. Only violation counts/rates, column names, timing and generic error classes are stored; sampled values never enter results, logs or APIs. Result history is retained for 90 days with bounded scheduled deletion. Edited definitions retain historical results but reset latest evidence; the new definition needs a new evaluation. The UI shows the latest 25 evidence records and filters by tenant/check.

Offline demo uses synthetic rows and existing schema snapshots. Every demo result is marked simulated, with deterministic missing amounts for Acme, duplicate order IDs for Cedar, an accepted-values example for Bluefin, and an additional schema column for Orbit. Creating other checks is supported against the demo catalog, but evidence remains synthetic.

## API

- `GET /api/quality/checks?tenant_id=&page=` lists definitions and their current latest evidence.
- `POST /api/quality/checks` creates a built-in definition; `PUT /api/quality/checks/{id}` edits it without changing its tenant.
- `PATCH /api/quality/checks/{id}` enables/disables with `{"enabled": true}`.
- `POST /api/quality/checks/{id}/run` evaluates an enabled check. Concurrent requests return 409.
- `GET /api/quality/results?tenant_id=&check_id=&page=` reads evidence history.

Example null-rate definition:

```json
{
  "tenant_id": "acme_retail",
  "name": "Order amounts present",
  "table_name": "orders",
  "kind": "null_rate",
  "params": {"column": "amount", "max_null_rate": 0.01},
  "sample_limit": 1000,
  "interval_sec": 900,
  "enabled": true
}
```

Local PostgreSQL verifies read-only execution, sample limits and statement timeouts. Redshift uses the documented [SET LOCAL syntax](https://docs.aws.amazon.com/redshift/latest/dg/r_SET.html). Validate the deployed role grants, workload controls, schemas and query cost in staging before enabling scheduled checks.
