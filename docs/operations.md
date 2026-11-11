# Operations

## Service health

- The API process health endpoint is `/api/health`.
- The API liveness endpoint is `/api/health/live`.
- Collector and alerter heartbeats are shown in Platform health and checked by their container probes.
- Monitor poll duration, poll errors, event lag and notification outbox depth.

## Backups and recovery

Use RDS point-in-time recovery as the primary AWS recovery path. Scheduled encrypted dumps are an additional recovery copy. Restore only into an empty, isolated database, then verify migrations and application data before a cutover. See [deployment](deployment.md#backup-and-restore) and [release checklist](release-checklist.md).

## Incident response

1. Check Platform health and the last successful Airflow, Airbyte and warehouse polls.
2. Open the affected tenant and run to inspect the classified cause and redacted log.
3. Follow the runbook guidance before taking an operator action.
4. Record the incident outcome and root-cause category.
5. If the console itself is degraded, check API health, worker heartbeats and database connectivity.

Operator actions and external writes are role-gated, audited and controlled by the live-action configuration.
