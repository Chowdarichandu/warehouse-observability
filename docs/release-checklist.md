# Release checklist

Use this checklist for each environment promotion. Attach command output, links to CI runs, and timestamped evidence to the release record. Use the same immutable image digests in dev, staging and production.

## Before staging

- [ ] Required verification and release-safeguard workflows pass for the release commit.
- [ ] Dependency and container reports have no unresolved release-blocking findings.
- [ ] Database migrations are reviewed and run as a pre-deploy job.
- [ ] A backup exists and the rollback image digests are recorded.
- [ ] Configuration uses the target environment's secret references and least-privilege roles.

## Staging acceptance

- [ ] Compare at least 20 sampled runs with their Airflow and Airbyte records.
- [ ] Complete one tenant onboarding and verify the shared-source tenant-isolation check.
- [ ] Complete one retry and one resync; verify operation records and audit entries.
- [ ] Verify SSO, role denial, logout and session revocation.
- [ ] Deliver a test notification through every enabled channel.
- [ ] Complete an isolated restore drill and verify the restored schema and application data.
- [ ] Rehearse rollback using the recorded image digests.

## Production promotion

- [ ] Confirm staging evidence is accepted and all release blockers are closed.
- [ ] Confirm the deployment references the exact staging-tested image digests.
- [ ] Confirm migration status, backup/PITR availability and alert routing.
- [ ] Verify service health, collector lag, notification delivery and audit writes after deployment.
- [ ] Record the release identifier, image digests, migration version and operator outcome.
