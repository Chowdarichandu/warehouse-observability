# Warehouse Observability

An in-house console for MySQL and MongoDB → Airbyte → Airflow → warehouse pipelines, with tenant health, run investigation, freshness, schema/volume changes, alerts, onboarding and audit history.

The offline demo works without cloud access. Live integration code, EC2 deployment configuration, and an EKS Helm chart are included. **Production release requires staging validation against your actual service versions and AWS account.** No production systems have been contacted or deployed from this workspace.

[Screen gallery](output/screenshots/README.md) · [Deployment guide](docs/deployment.md) · [Airflow/DAG setup](airflow/dags/README.md) · [Configuration reference](docs/environment.md) · [Vercel/Railway demo](docs/hosting.md) · [Implementation status](MILESTONES.md)

## Run the offline demo

```bash
cp .env.example .env
make install
make demo
```

Open **http://localhost:8080**. Sign in with `admin@demo.local`, `operator@demo.local`, or `viewer@demo.local`; password `demo` (override with `DEMO_PASSWORD`). Use localhost for the HTTP demo's Secure cookies. HTTPS is required in live deployments.

Docker Compose starts Postgres 16, FastAPI, collector, alerter and the web proxy. Once images/dependencies are cached, demo operation makes no external calls. Without Docker, the native runner uses Python 3.11+, Node 22+, npm and PostgreSQL 16 binaries at `/usr/lib/postgresql/16/bin`. It creates an isolated loopback database on 55432, API on 8000 and Vite server on 8080. The machine's existing database is untouched; `.runtime` links to a private `/tmp` directory.

```bash
make up          # Empty local workspace with demo accounts
make demo        # Idempotent seven-day seed and live simulator
make down        # Stop this project's local services
make reset       # Delete this project's local demo data
make seed        # Reapply the seed if empty
make types       # Regenerate OpenAPI and frontend types
make lint        # Python/TypeScript lint, formatting and type checks
make test        # Backend integration/security tests and frontend tests
make e2e         # Browser walkthrough against a running demo
make build       # Frontend production build
```

Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to an installed Chromium, or run `npx playwright install chromium` once in `frontend`. Run `python scripts/gallery.py` in the project virtual environment to rebuild the offline screen gallery and ZIP.

## Live operation

The [deployment guide](docs/deployment.md) covers EC2 and EKS, private RDS, ECR image digests, HTTPS/ACM, scoped IAM roles, Secrets Manager, OIDC groups, notification channels, backups, probes and rollback. Use `.env.live.example` and `config/live.example.yaml` as reviewed templates; example IDs are not working credentials.

- Airflow 2/3 REST clients use separate read/write credentials. MWAA uses IAM/SigV4. DAG IDs, API prefixes and tenant connection mappings are explicit configuration. Airflow 2 BasicAuth alone does not accept the bearer-token transport; configure the deployed auth manager/gateway accordingly.
- The collector has overlapping watermarks, bounded pagination, unfinished-run revisits, isolated per-task failures, redacted logs and natural-key upserts. Linked Airbyte jobs are not inserted a second time. PostgreSQL and Redshift use catalog row estimates rather than full-table counts.
- Live writes are disabled until `LIVE_ACTIONS_ENABLED=true`; registry pause/resume/onboarding also requires reviewed runtime-driven DAGs. Unsafe mapped retries on Airflow 2 are rejected. Every requested/confirmed/failed operation is audited; ambiguous writes require review before replay.
- Onboarding validates source TLS/connectivity/CDC permissions and a pre-created destination namespace, resolves only approved AWS secret paths, then invokes a durable provisioning DAG. Connector configurations and streams must match the deployed Airbyte version. The source-check step currently targets the OSS config API; validate/extend it before using Cloud.
- Slack, Teams, TLS SMTP, SES and SNS use a database outbox with bounded retries, lease recovery and delivery diagnostics. Demo messages remain simulated. Actual deliveries are at least once; provider-side duplicates remain possible after a process crash.
- OIDC uses authorization code + PKCE, one-use state, nonce, signature/issuer/audience checks, verified email and explicit group-role mapping. Live mode creates no demo users and disables password login. Sessions are stored server-side and revoked on logout; administrators can revoke a user's sessions.
- Scheduled retention preserves daily run aggregates; failed logs are kept 90 days, runs 13 months and raw snapshots/platform history 30 days. Encrypted S3 backups use `pg_dump`; restore refuses a database that already contains user tables. Use RDS PITR as the primary recovery mechanism.

## Investigation and release upgrades

- **Dependencies:** explore source, DAG/task, Airbyte connection and warehouse assets, inspect relationship evidence, and identify potentially affected downstream assets. Configured dependencies are distinguished from observed links; this is not verified SQL lineage.
- **Data quality:** configure null-rate, duplicate-key, accepted-value and schema-contract checks. See aggregate results and history, edit schedules, and run an individual check. Demo evidence is synthetic; live reads require `QUALITY_ENABLED=true`, reviewed permissions and enabled live actions for operator requests.
- **Investigation:** save private run filters to your account, compare runs and stream counts, navigate matching log lines, and follow runs/alerts/onboarding/actions/checks in the Activity timeline.
- **Release safeguards:** scheduled dependency/container audits, isolated PostgreSQL restore drills, a bounded viewer load test, and exact-digest image signing/verification. See [the release guide](docs/release-safeguards.md), [dependency evidence](docs/dependencies.md), and [quality configuration](docs/quality.md).

## Demo walkthrough

Start at the overview and open Acme Retail's failed MySQL CDC run to inspect its binlog diagnosis and redacted log. A simulated retry completes in roughly 30 seconds; only the demo resync repairs the missing replication position. Bluefin is near its freshness SLA, Northwind has a stuck CDC run, Orbit has a volume drop/schema change, and Cedar has nighttime failures. Explore the alert lifecycle, then onboard `zenith_pay` in about a minute. Platform, Administration, dark theme, TV and mobile views are included.

Metrics follow SPEC §7: successful runs only for duration percentiles; success/(success+failed) for success rate; source freshness against each tenant's SLA; compliance in five-minute buckets excluding time before registration and weighting total observed buckets. The demo's Bluefin recovery resolves the spec's conflicting latest-failure/degraded scenario without changing the health formula.

## Verification limits

Contract fixtures are synthetic and sanitized, not staging recordings. Local tests cover offline workflows, session revocation, signed OIDC login, IAM request shapes, client versions, redaction, ingest deduplication, notification retries, durable actions, catalog snapshots and a real local PostgreSQL backup/restore roundtrip. Helm templates are linted/rendered. See `output/verification.json` for the most recent recorded run.

Before release, complete SPEC's 20 staging run comparisons, one staging onboarding/retry, real chosen alert/SSO providers, a container/deployment run, and recovery/rollback acceptance. [The repository's original broader vision](docs/repository-vision.md) is preserved. Configured/observed dependency maps and built-in sampled quality checks are now implemented; verified SQL/column/dashboard lineage, arbitrary SQL checks and per-tenant cost remain future scope.


Seven-DAG onboarding is currently available in the offline demo. Live onboarding and resume are deliberately disabled until staging verifies DAG recovery and enforces filtering on the shared MongoDB document field `tenant_id`. The deployed connector must prove the field's value maps to the correct tenant and cannot sync documents belonging to another tenant. Existing unrelated pipeline monitoring remains available.
