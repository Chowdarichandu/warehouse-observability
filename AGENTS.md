# AGENTS.md

How to work in this repository. It applies to every contributor, human or coding agent.

## Read first

1. [`SPEC.md`](SPEC.md): what the product does and how it's built. It is the source of truth.
2. [`docs/DESIGN.md`](docs/DESIGN.md): the design system and every screen. It is part of the spec.

When the code and the spec disagree, the spec wins. When the spec is unclear, make the smallest reasonable assumption, state it in the pull request, and keep going.

## Current program: the v3 rebuild

- Work through SPEC §17 milestones R0 to R8, in order. Open one pull request per milestone; in R5, open one per screen.
- **Rebuild in place.** Start each milestone by reviewing the existing code in that area. Keep what meets the spec and passes its tests; replace the rest. Record each keep-or-replace decision in the pull request description.
- **The frontend is rebuilt on the design system.** Delete each old component once its screen has migrated, and leave nothing unused behind.
- Repository cleanup (below) is part of R0.

## Non-negotiables

1. `make demo` works offline at every commit.
2. Code and tests never contact external or production systems. Tests use recorded, sanitized fixtures.
3. The server enforces RBAC on every endpoint. Every write is role-checked, idempotent and audited.
4. Secrets never appear in the repository, logs, the database or the browser.
5. UI code uses design tokens only. Lint enforces this.
6. Never weaken or delete a test to make a build pass. Fix the code, or update the spec first.

## Stack and conventions

**Backend**

- Python 3.12.
- Libraries: FastAPI, psycopg 3 (plain SQL in repository modules, no ORM), pydantic v2 with pydantic-settings, httpx, APScheduler, argon2-cffi, and an OIDC client library. Libraries already in the repository for these concerns can stay.
- Type hints everywhere. ruff for lint and format; mypy strict for `backend/obs`; pytest.
- Migrations are numbered, forward-only SQL files in `sql/migrations/`. Never edit a migration that has already been applied.
- Timestamps are `timestamptz` in UTC. The API returns ISO-8601 UTC.
- Logs are structured JSON with request ids, and all error and log text passes through redaction.
- Domain exceptions map to the API error shape in SPEC §9.1.

**Frontend**

- React and TypeScript in strict mode, built with Vite.
- Libraries: Radix UI primitives, TanStack Query and TanStack Table, one chart library, and IBM Plex fonts from `@fontsource`.
- API types are generated from OpenAPI (`make types`). Never hand-write API response types.
- Server state lives in TanStack Query. Filters and tabs live in the URL. Add a global store only for real cross-screen client state.
- Tooling: ESLint and Prettier, Vitest for unit and component tests, Playwright for end-to-end tests.
- Every interactive element is reachable by keyboard and passes axe.

## Commands

| Command | What it does |
|---|---|
| `make install` | Install backend and frontend dependencies |
| `make up` | Start the stack in the current `MODE` |
| `make demo` | Seed the demo dataset and start the stack with live simulation |
| `make down` / `make reset` | Stop the stack / stop it and delete local data |
| `make seed` | Re-apply the demo seed |
| `make types` | Regenerate the OpenAPI schema and frontend types |
| `make lint` | ruff, mypy, ESLint, tsc, Prettier check, token lint |
| `make test` | Backend unit, contract and integration tests, plus frontend tests |
| `make e2e` | Playwright walkthrough, visual regression and axe, against a running demo |
| `make build` | Production frontend build and container images |
| `make gallery` | Regenerate `docs/screenshots/` from demo mode |
| `make loadtest` | Capacity test against the scaled demo dataset |

## Branches, commits and pull requests

- Name branches `r<milestone>-<topic>` during the rebuild, and `feat/…` or `fix/…` after it.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`).
- Every pull request description has these sections:
  - **Summary**
  - **Spec references:** SPEC and DESIGN sections.
  - **Keep or replace decisions:** during the rebuild only.
  - **How it was verified:** the commands and tests run.
  - **Screenshots:** for UI changes, in light and dark at 1440 and 390 px.
  - **Follow-ups**
- Add a `CHANGELOG.md` entry under **Unreleased** for every change a user would notice.

## Definition of done (every pull request)

- `make lint`, `make test` and `make e2e` pass.
- `make reset && make demo` shows every SPEC §13 scenario.
- New endpoints appear in OpenAPI, and the frontend types are regenerated.
- New endpoints have RBAC tests for every role, and every new write produces an audit entry.
- New configuration is added to `.env.example` and `.env.live.example`, and to `docs/configuration.md`.
- UI changes meet the DESIGN §12 definition of done.
- Documentation affected by the change is updated in the same pull request.

## Writing in this repository

Documentation is part of the product. Follow these rules in docs, code comments, commit messages and UI copy:

- **Use the product voice.** Describe what the product does and how to use it, in the present tense and plain language.
- **Keep internal context out of the repository.**
  - Don't refer to specific people, job titles, internal meetings, or conversations.
  - Don't mention which tools were used to write the code.
  - Don't write progress narration or session notes in docs ("implemented X today", "as requested"). Progress belongs in pull requests and `CHANGELOG.md`.
- **Write constraints as product behavior or requirements**, not as disclaimers. For example: "Live actions are off until `LIVE_ACTIONS_ENABLED=true`." Release requirements live in `docs/release-checklist.md`.
- **Use fictional examples only.**
  - Hosts use `example.com`, and tenants are fictional.
  - No real hostnames, account ids, client names or customer data anywhere.
- **UI text** follows the copy rules in DESIGN §10.

## Repository cleanup (part of R0)

- Remove `SPEC.original.pdf` and `AGENTS.original.pdf`.
- Replace `MILESTONES.md` with `CHANGELOG.md` (summarize the earlier work as 0.x entries) and `docs/release-checklist.md`.
- Replace `README.md` with the product README.
- Fold anything still relevant from `docs/repository-vision.md` into `SPEC.md`, then delete the file.
- Remove session notes and internal references from every doc, following the writing rules above.
- Move the screenshot gallery to `docs/screenshots/`. Stop tracking generated output (`output/`) and add it to `.gitignore`.
- Add secret scanning (gitleaks) to CI, and fail the build on any finding.

## Don't

- Don't add infrastructure the spec doesn't name (Redis, Kafka, Elasticsearch and so on) without changing the spec first.
- Don't let the browser call Airflow, Airbyte or the warehouse directly. Everything goes through `/api/v1`.
- Don't store free-form SQL in alert rules or quality checks. Both use built-in types with parameters.
- Don't run `count(*)` on warehouse tables. Use catalog statistics.
- Don't modify existing pipeline DAGs from this repository. Ship the adoption guide in `airflow/dags/` instead.
- Don't accept raw credentials in any form or API. Secret-manager references only.
