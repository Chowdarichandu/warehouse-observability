# Implementation and verification status

The original M0–M4 offline demo is implemented and remains the default `make demo` path. The user authorized continuing beyond the original review stop on 2026-11-09 and requested EC2/EKS support and a repository push.

- **M0–M4:** offline seed, read API, roles/audit, all console views, simulated actions/alerts/onboarding, SSE, walkthrough and screenshots.
- **M5 code:** version-specific Airflow/Airbyte clients, MWAA IAM transport, pagination/watermarks, unfinished-run revisits, tenant resolution, job linking, idempotent ingest, redaction, catalog-based PostgreSQL/Redshift snapshots, platform diagnostics and contract fixtures.
- **M6 code:** guarded real retry/pause/onboarding, durable operation outcomes and reconciliation, TLS source preflight, secret references, durable provisioning resources, reference registry/onboarding DAGs, reviewed migration instructions.
- **M7 code:** OIDC authorization-code flow with PKCE/state/nonce/signature/issuer/audience checks, explicit group roles, revocable sessions, durable notification outbox, retention/rollups, encrypted backup/empty-target restore, non-root images, EC2 Compose, EKS Helm, IAM examples, CloudWatch alarms and CI/ECR workflows.

**Release acceptance remains external:** no AWS or production systems were contacted. The SPEC acceptance criteria requiring 20 staging run comparisons, one real staging onboarding/retry, a chosen SSO/alert provider, and a shared environment deployment cannot be claimed from local contract fixtures. See `docs/deployment.md` and `tests/fixtures/README.md` for the exact evidence required. Docker images, actual Airflow DAG imports, EC2/EKS rollouts and account permissions still need an environment run.


- **Enhancements 4–7:** evidence-based dependency maps, sampled data-quality checks with persisted history/scheduling, private saved views/run comparison/log navigation/unified activity, and automated release safeguards. Production lineage, full-table quality guarantees, actual workload capacity and AWS rollout acceptance require environment-specific evidence.
