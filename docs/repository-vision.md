# Warehouse Observability

End-to-end observability for data warehouses and lakehouses — know when data is late, wrong, or missing *before* your stakeholders do.

## What it monitors

- **Freshness** — time since each table / partition was last successfully updated, against its SLA
- **Volume** — row-count anomalies, unexpected drops / spikes, zero-load failures
- **Schema** — column adds / drops / type changes, breaking-change alerts
- **Data quality** — null rates, uniqueness, referential integrity, custom SQL checks
- **Pipeline health** — job failures, duration drift, cost / credit spikes

## Goals

- One place to see the health of every critical table
- Alert on symptoms (stale / broken data), not just job failures
- Lineage-aware impact: which dashboards and downstream tables a failure affects

## Status

🚧 Initial setup — structure and first checks in progress.

## Planned structure

```
warehouse-observability/
├── checks/          # Freshness, volume, schema and quality check definitions
├── alerts/          # Alert routing and severity rules
├── dashboards/      # Observability dashboards / queries
└── docs/            # Design notes and runbooks
```

## Stack (target)

- Warehouses / lakehouses: Snowflake, Databricks / Delta Lake
- Pipelines: Spark / PySpark, Airflow
- Checks run as SQL / Python, results stored in a meta table for trending

## License

MIT
