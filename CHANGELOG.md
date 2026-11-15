# Changelog

User-visible changes are recorded here. Entries are grouped by release; version numbers describe the repository history before the v3 rebuild.

## Unreleased

<<<<<<< HEAD
- Use Pravah branding in the sign-in screen, workspace header and browser titles. Planned modules now stay non-interactive until their screens are available, and live onboarding messages explain the tenant-isolation gate.
=======
- Move the screenshot gallery into `docs/screenshots/` so the README hero image and gallery links render on GitHub. Generate runtime configuration reference types and hide credential defaults, merge the duplicate environment guide, and rename the EC2 unit to `pravah.service`.
>>>>>>> origin/r0-repo-review
- Fix hosted demo deploys failing their healthcheck on a fresh database: the start script now starts the API right after migrations and seeds afterwards, instead of blocking the server behind a seed that takes minutes over the network. The demo seed also commits in sections instead of one long transaction, so the API's startup inserts never wait on it and an interrupted seed resumes instead of restarting from zero.
- Show the planned product modules (HRMS, Finance, SAP, POS, Inventory, Support, Hospitality) in the product picker: migration 017 enables them in the registry, so admins see them and access is still gated per role and per user.
- Move the sidebar Collapse control to the top of the sidebar, next to the brand.
- Give account Settings its own (gear) icon; it previously shared the Administration sliders icon.
- Animate theme switching: surfaces now fade between light and dark instead of snapping.
- Open dependency details in view: clicking a node in the dependency map scrolls its detail panel into view.
- Clarify saved views on Pipeline runs: the block is labelled "Saved views" and explains that a view stores the current filters and time range.
- Spacing pass: the top search box gets real padding, side-by-side panels stack instead of squeezing at laptop widths, and stacked panels get more air.
- Fix demo onboarding stalling for MySQL-only tenants: the simulated seven-DAG progression job is now created for every demo onboarding, not only when MongoDB is enabled.
- Fix dialogs overflowing small viewports: modals now cap at the viewport height and scroll internally, so the title and close control stay reachable (the User permissions dialog outgrew the screen as the permission catalog grew).
- Fix incident responses masking console usernames: acknowledged-by, resolved-by, assignee and note-author fields are no longer redacted as if they were secrets (free text such as note bodies still is).
- Add maintenance windows: operators can schedule per-tenant windows; runs inside a window are tagged in-maintenance, excluded from SLA buckets, and never raise consecutive-failure alerts. The demo seeds Cedar Foods with a nightly window.
- Add an SLA breach forecast on the Freshness screen: tenants whose data will cross the freshness SLA before the next scheduled run are listed with the time remaining.
- Add the demo Dev mailbox (admin only): invite and password-reset emails are captured in the console instead of being sent.
- Pre-fill the onboarding wizard with the Zenith Pay demonstration tenant, matching the documented scenario.
- Add the Incidents screen: grouped incidents with a timeline, acknowledge, assign, notes, and resolve with an optional root-cause category.
- Fix demo tenant-isolation checks raising a critical incident for every shared-source tenant: demo isolation evidence no longer depends on the table catalog, quality checks name tables that exist in each tenant's catalog, and the demo dataset gains the Pinecrest Education tenant with its resolved isolation incident and check history (replacing Luminous Labs).
- Add recorded contract fixtures for every supported Airflow (2.x, 3.x) and Airbyte endpoint family, replayed through the clients in tests.
- Expand the observability data model with shared metric definitions, incident and operations records, retention rollups, and a product-module access registry.
- Add module-aware navigation and grants, incident response APIs, durable notification delivery, and a responsive IBM Plex design system.
- Start the v3 foundation work: repository guidance, configuration guards, generated API documentation and full-history secret scanning.
- Allow isolated native demo instances with their own runtime directory and ports; model the demo CDC incident as a recoverable eight-hour outage.

## 0.7.0

- Add durable operator workflows, shared-source tenant-isolation checks, release safeguards and AWS deployment references for EC2 and EKS.

## 0.6.0

- Add OIDC sign-in, server-side session controls, role permissions, onboarding progress and administration tools.

## 0.5.0

- Add freshness, volume, schema and quality views, dependency evidence, saved views and investigation tools.

## 0.4.0

- Add Airflow and Airbyte collection interfaces, error classification, log redaction and warehouse catalog snapshots.

## 0.3.0

- Add tenant and run exploration, alerts, audit history and simulated recovery actions.

## 0.2.0

- Add the offline, seeded demo with a live ticker and role-based console navigation.

## 0.1.0

- Establish the first console shell and PostgreSQL-backed observability API.
