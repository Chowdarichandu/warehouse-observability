# Observability Console

An in-house observability application for MySQL and MongoDB → Airbyte → Airflow → warehouse pipelines. This implementation stops at the **M4 demo review boundary** in SPEC.md. It does not contact production systems.

[Browse the screenshots](output/screenshots/README.md) or [open the offline gallery](output/screenshots/index.html) for full-resolution Playwright captures of all main views, dark theme, TV mode, and mobile. These are screenshots of the running demo. The verified walkthrough covers simulated actions; production integrations and hardening remain at M5–M7.

## Run

With Docker Compose installed:

```bash
cp .env.example .env
make demo
```

Open **http://localhost:8080**. Sign in as `admin@demo.local`, `operator@demo.local`, or `viewer@demo.local` with password `demo` (or `DEMO_PASSWORD` from `.env`). TV mode: http://localhost:8080/?tv=1.

The five services are Postgres 16, FastAPI, collector, alerter, and nginx/React. Only port 8080 is published. On first use, Docker needs network access to obtain images and build dependencies. Once cached, the demo makes no external calls.

### Without Docker

The same Make targets support local development with Python 3.11+, Node 22+, npm, and PostgreSQL 16 binaries at `/usr/lib/postgresql/16/bin`:

```bash
make install
make demo
```

The native runner creates an isolated database on **127.0.0.1:55432**, an API on **127.0.0.1:8000**, and the Vite web server on **127.0.0.1:8080**. It does not touch the machine's existing PostgreSQL cluster. Data and process logs live under `.runtime/`, a link to a private directory in `/tmp` so PostgreSQL works on storage filesystems that do not support Unix permissions. The temporary directory may be cleared on reboot; the demo can always be reseeded. Set `OBS_NATIVE=1` to use this runner even when Docker is installed. Native database authentication is trusted on loopback only, for local development.

```bash
make up           # Empty console with demo logins; no ticker
make demo         # Idempotent seed + all demo services
make seed         # Keep existing history; create it if absent
make down         # Stop owned services
make reset        # Delete this project's demo database/volume
make demo         # Recreate a fresh seven-day dataset
```

`make live` intentionally fails at M4. Live clients and actions belong to M5/M6. Setting environment variables does not silently enable unfinished integrations.

## Demo walkthrough

1. Start on the overview, or use the TV button. Ten fictional tenants have about 6,700 runs. Status changes and activity arrive through Postgres LISTEN/NOTIFY → SSE, with 30-second polling fallback.
2. Open Acme Retail → a red MySQL CDC timeline block → classified `MYSQL_BINLOG_PURGED` error, resync hint, and redacted log. Retry creates a new run, which succeeds after about 30 seconds. Acme remains down because the next simulated CDC check still fails. Admins can use **Simulate resync** to restore its replication position.
3. Open Errors with a seven-day range. Inspect grouped failures, the Cedar Foods nighttime heatmap, and mean time to recovery.
4. Open Runs to filter, sort, paginate, and export the whole filtered result as CSV. Northwind has a CDC run stuck above its seven-day median.
5. Open Freshness & volume. Bluefin's Mongo source is near its SLA; Orbit Logistics has a roughly 40% table-volume drop and an added `delivery_region` column.
6. Open Alerts. Acknowledge a critical CDC-position alert. Admins can edit built-in rule parameters and send a **local simulated** Slack/Teams/email test. Deliveries are stored in `obs.notification_deliveries`; no messages leave the laptop.
7. Onboard `zenith_pay` with the wizard's defaults. Six durable steps complete in about 60 seconds, and the tenant turns healthy on the overview. To repeat this exact slug, reset the demo first or choose a different slug.
8. Inspect the repaired DAG import error in Platform history and audited actions in Administration. Try the viewer login to verify access restrictions.

## Validation

Start a demo before integration and browser tests:

```bash
make types        # Export FastAPI OpenAPI and regenerate TypeScript; commit both outputs
make lint         # Ruff, ESLint, Prettier, strict TypeScript
make test         # Backend security/data/metric tests + frontend Vitest
cd frontend
npx playwright install chromium  # One-time browser setup, requires network
cd ..
make e2e          # Full walkthrough, retry, onboarding, roles, theme, TV and mobile
make build        # Production frontend build
```

If a compatible Chromium is already available, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to its absolute executable path. Screenshots are saved under `output/screenshots/`; Playwright failures retain traces and screenshots under `frontend/test-results/`.

`make e2e` also captures the remaining console screens. Run `python scripts/gallery.py` with the project's virtual environment to rebuild the offline gallery and `output/console-screens.zip` download.

## Decisions and assumptions

- Backend SQL views implement SPEC §7. Success rate excludes queued, running, cancelled, and skipped runs. Duration statistics use successful runs. SLA compliance uses five-minute buckets and success timestamps. Buckets before tenant registration are excluded, and overall compliance weights observed buckets rather than averaging percentages across tenants of different ages. The demo has seven days of data; unobserved older buckets are non-compliant in the 30-day metric.
- The spec calls Bluefin degraded while also saying its Mongo CDC failed. Under its exact health formula, a latest failed CDC run would mean down. The demo retains a three-attempt failure followed by a recovery 100 minutes before seeding. This makes it degraded and near its SLA without changing health logic. It will naturally age into a breach if the demo is left running.
- Seed durations follow tenant-specific log-normal distributions. Ticker batches represent newly collected completed runs, with start/end times covering their reported durations. Bluefin's recovery and Northwind's stuck run are held visible. Seed data is deterministic relative to the seed time, with a fixed random seed.
- Retry completion and onboarding are database jobs with row locks and durable progress, so restarting the worker does not lose actions. The Acme retry succeeds as a task attempt but is followed by a new scheduled failure; a resync stops its recurring binlog errors. Historical errors remain, so health can remain degraded after resync.
- Passwords use Argon2. Session cookies are httpOnly, Secure, SameSite=Lax; mutating requests also require a JWT-bound CSRF token and matching Origin when provided. Use **localhost** for the HTTP demo, where Chromium permits Secure cookies. Use HTTPS for deployment.
- Error messages and logs are redacted on write and again on read. Owner email and audit actor fields are redacted in console data; authenticated identity and admin user management retain account emails for access control.
- Pause/resume follows the explicit API table: Admin only. Retry, alert actions, and onboarding are Operator/Admin. Every successful mutation, including login, logout, preflight, and tests, is audited.
- Extra demo endpoints: `/api/tenants/{id}/resync`, `/api/users`, and `/api/users/{id}`. These are documented in OpenAPI along with the specified endpoints.

## Remaining milestones

- **M5:** recorded Airflow/Airbyte fixtures, version-specific clients, linking and tenant resolution, live warehouse adapters, platform checks, and validation of 20 staging runs.
- **M6:** real retry/pause/onboarding, source preflight checks, and reviewed registry-driven DAG changes. This repository does not edit the team's existing DAGs.
- **M7:** OIDC and group mapping, retention/rollups, backup/restore, deployment, and security review.

The deployed Airflow and Airbyte versions, warehouse engine, tenant mapping, secret manager, alert destination, SLAs, and on-call ownership still need the team's answers. See SPEC §19.
