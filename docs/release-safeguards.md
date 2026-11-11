# Release safeguards

Pull requests and pushes to `main` run verification and release-safeguard workflows. The safeguards require no AWS credentials or production integrations.

## Repository secrets

Gitleaks scans the full Git history for each pull request and main push. The scan fails the job when it finds a secret. Do not add real credentials to source, fixtures, screenshots, workflow artifacts or documentation. If a credential was committed, revoke it and remove it from Git history using the repository's incident process; deleting the current file is not enough.

## Dependencies and images

- `pip-audit` checks the pinned Python requirements.
- `npm audit --audit-level=high` checks the frontend dependency graph.
- Grype scans the API and web container images. The report includes known findings; the release gate blocks fixable high and critical vulnerabilities.
- Workflow actions and container base images are pinned. Review version and digest changes through pull requests.

Configure branch rules to require `test`, `containers`, `secrets`, `dependencies`, both `images` matrix jobs and `recovery` before merging.

## Image publication

The manual ECR workflow accepts `main` only and checks for successful verification and safeguard runs for the exact source commit. It builds immutable image digests with SBOM and provenance attestations, scans the published digests, signs them with Cosign and verifies the exact workflow identity and source SHA. Publishing does not deploy an image.

Verify a published digest against the exact repository and workflow identity. Replace the placeholders with the release repository and commit:

```bash
cosign verify \
  --certificate-identity 'https://github.com/OWNER/REPOSITORY/.github/workflows/publish.yml@refs/heads/main' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  --annotations "git_sha=$RELEASE_SHA" \
  "$IMAGE_REPOSITORY@$IMAGE_DIGEST"
```

## Read-only load smoke

The default load smoke targets `http://localhost:8080`. It uses bounded read-only endpoints, a demo Viewer account and fixed limits for request count, concurrency, rate and duration. It does not trigger runs, change tenants or send alerts.

For a staging target, supply an authenticated Viewer session through `OBS_LOAD_SESSION` and explicitly confirm the HTTPS origin:

```bash
.venv/bin/python scripts/load_test.py \
  --base-url https://console.staging.example.com --confirm-staging \
  --requests 200 --concurrency 4 --rate 20 \
  --max-p95-ms 1500 --max-error-rate 0
```

Do not pass session values as command-line arguments or include them in logs. The tool leaves a supplied session active; revoke it after the smoke.

## Isolated recovery drill

The recovery drill creates uniquely named scratch databases on a local PostgreSQL 16 service, applies migrations, writes synthetic rows, dumps and restores the data, compares table contents and checks that restore refuses a non-empty target. Scratch databases are dropped when the drill finishes.

For a local run, set `OBS_DRILL_ADMIN_DSN` to a dedicated loopback PostgreSQL role with `CREATEDB`, make PostgreSQL 16 tools available, then run:

```bash
PATH=/usr/lib/postgresql/16/bin:$PATH \
  .venv/bin/python scripts/recovery_drill.py --confirm-isolated
```

The drill does not call AWS. Use the [release checklist](release-checklist.md) for staging backup, restore, IAM/KMS, RDS recovery and rollback evidence.
