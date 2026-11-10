# Pipeline dependency map

Open **Pipeline dependencies** and choose a tenant. Select a node to inspect the underlying relationship evidence and its potential downstream impact. The tenant and selected node are encoded in the URL so an investigation can be shared. Nodes are normal keyboard-operable buttons; the wide graph scrolls on narrow screens and supports both themes.

The authenticated read-only `GET /api/dependencies?tenant_id=<slug>` endpoint derives its map from existing observability metadata. It never contacts Airflow, Airbyte, or the warehouse. Viewers can inspect it. The tenant picker uses `GET /api/dependencies/tenants?q=<name-or-slug>&page=<number>` with 50 results per page and literal substring search; it can reach tenants beyond the initial page without calculating workspace-wide SLA metrics. Its search and page are reflected in the URL.

- **Configured** source-to-connection relationships come from the tenant's Airbyte connection mappings. Connection-to-schema relationships describe the configured tenant destination; they do not prove a successful write.
- **Observed** DAG/task membership and task-to-connection relationships come from collected pipeline-run links. The latest execution supplies the task or connection status and investigation link; re-polling an older run does not overwrite the latest execution's status. “Last observed” is the collector timestamp for that execution.
- **Observed** schema membership comes from collected warehouse catalog snapshots. A table's presence does not confirm which connection populated it.

Downstream impact is graph reachability: assets potentially exposed to a failure. It is not a list of confirmed failures. Shared DAG and connection IDs are scoped to the selected tenant so metadata cannot accidentally link tenants. Missing execution links remain missing. This release does not claim SQL, column, dashboard, or record-level lineage and does not infer table producers from matching names.

The response bounds an all-tenant request to 100 tenants, 2,000 distinct run relationships and 2,000 latest catalog tables, returning `truncated=true` when any bound is exceeded. Select an individual tenant to reduce the scope. The UI displays a limit warning; it does not silently represent an incomplete map as complete.

No migration, external service, secret, or feature flag is required. Offline demo metadata produces the same map shape as live metadata. Later OpenLineage ingestion can add separately attributed evidence once the actual Airflow/provider versions and destination identifiers have been validated in staging.
