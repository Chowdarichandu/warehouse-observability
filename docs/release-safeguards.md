# Release safeguards

The verification workflow now includes a small authenticated read-only load smoke. The separate **Release safeguards** workflow runs on every pull request, main push, Monday at 04:17 UTC, and manual dispatch. It needs no AWS access or application secrets.

## Dependency and image gates

- `pip-audit==2.10.1` checks the complete pinned Python lock, including development dependencies. Any published Python advisory fails the job.
- `npm audit --audit-level=high` checks the frontend production and development dependency graph. High or critical findings fail; lower severities remain in its JSON report.
- The actual API and web Dockerfiles are built, then scanned with Grype `v0.121.2` through an immutable Anchore action commit. An unrestricted JSON report records known findings, including those with no fix. A second scan fails for **fixable high or critical** vulnerabilities. There is no global CVE ignore list. Review unfixed findings separately and record any release exception with an owner and expiry.
- Reports are retained as workflow artifacts for 30 days. Failed downloads or advisory database errors fail checks; they do not report a clean scan.
- Third-party workflow actions are pinned to commit SHAs. Update pins, scanner/tool versions and base image digests through reviewed changes; regular scans still use current advisory data.

Base image patches were verified against the official Docker Hub repositories on 2026-11-09 and pinned to their multi-platform manifest digests: Python 3.11.18 (Bookworm), PostgreSQL 16.15 (Bookworm), Node 22.23.4 (Bookworm), and nginx 1.28.3 (Alpine 3.23). The web build also applies the Alpine branch's available package security updates before dropping privileges. Keep the existing major/runtime branches compatible while reviewing future scanner findings. Sources: [Python tags](https://hub.docker.com/_/python/tags), [PostgreSQL tags](https://hub.docker.com/_/postgres/tags), [Node tags](https://hub.docker.com/_/node/tags), [nginx tags](https://hub.docker.com/_/nginx/tags).

Configure branch protection/rulesets to require `test`, `containers`, `dependencies`, both `images` matrix jobs and `recovery` before merging. GitHub account settings are not changed by this repository. Scheduled failures appear in GitHub Actions; configure repository notifications or your existing incident integration for them.

## Digest signing and publishing

The manual ECR workflow accepts only `main` and requires successful **Verify console** and **Release safeguards** push runs for the **exact source commit**. It keeps the existing protected `image-publishing` environment, GitHub OIDC AWS role, BuildKit SBOM and provenance outputs. No deployment is automatic.

After publishing, it scans each exact ECR digest, signs it using Cosign `v3.1.4` and the workflow OIDC identity, and immediately verifies both signatures and the source-SHA annotation. Scan/sign failures leave an unsigned image in ECR; only the fully successful workflow is release evidence. Keep unsigned images out of deployments. The build role needs the existing scoped ECR pull/push permissions; signature OCI artifacts also need ECR write permissions. Test the registry's OCI artifact support in staging.

Keyless signing records image and workflow identity metadata in the public Sigstore transparency log. The images can remain private in ECR. Use the exact repository/workflow identity, issuer and SHA when independently verifying; never accept any identity with a wildcard:

```bash
cosign verify \
  --certificate-identity 'https://github.com/Chowdarichandu/warehouse-observability/.github/workflows/publish.yml@refs/heads/main' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  --annotations "git_sha=$RELEASE_SHA" \
  "$IMAGE_REPOSITORY@$IMAGE_DIGEST"
```

Deploy the verified digest through EC2 or Helm. Signing checks are supplied here; an EKS admission controller that rejects unsigned images is not installed.

## Read-only load smoke

Start the offline demo, then run:

```bash
.venv/bin/python scripts/load_test.py
```

The default is `http://localhost:8080`, 200 requests, four workers, at most 20 requests/second, p95 ≤1500 ms and zero errors. It logs in once as the demo viewer and revokes its own session afterward. Normal CI uses a smaller smoke (20 requests, two workers, four requests/second, p95 ≤3000 ms). This validates a basic responsiveness budget, not production capacity.

The tested paths are a fixed allowlist: overview, tenant list, paginated runs and freshness. All load requests use GET. Redirects are rejected, responses are capped at 1 MiB, and connections have bounded timeouts. Request count, concurrency and rate are capped at 10,000, 50 and 200/s; the schedule is limited to five minutes. Network requests that are already in flight can take up to the configured ten-second timeout to finish. p50/p95 measure request duration, excluding deliberate rate-limit waiting. Connection errors, non-200 responses and oversized responses fail the error budget.

For an approved staging console using OIDC, sign in as a dedicated **viewer**, place its `obs_session` cookie in the local `OBS_LOAD_SESSION` environment variable, and run:

```bash
.venv/bin/python scripts/load_test.py \
  --base-url https://observability.staging.example.com --confirm-staging \
  --requests 200 --concurrency 4 --rate 20 \
  --max-p95-ms 1500 --max-error-rate 0
```

Do not paste session values into issues, terminal commands saved in history, or workflow output. The tool prints aggregate timings/errors only and leaves a supplied session active; revoke it when finished. It requires HTTPS and explicit confirmation for any non-loopback origin, rejects URL credentials/paths/query strings, and does not perform password login against live mode. It never triggers runs, changes tenants or sends alerts. No production load run has been performed.

## Isolated recovery drill

The scheduled job creates **two new uniquely named scratch databases** on its local PostgreSQL 16 service. It applies all current migrations to the source, writes synthetic tenant/run/log/user fixtures, uses the application's `pg_dump`/`pg_restore` implementation, compares content fingerprints for every application table, checks a restored sequence's next value and verifies that a second restore is refused because the target is no longer empty. Both scratch databases are dropped on success or failure. No existing application database is backed up, restored or deleted.

To run locally, use a dedicated local PostgreSQL server with `CREATEDB` and the role permissions required by migrations. Set `OBS_DRILL_ADMIN_DSN` privately to its loopback admin DSN, make PostgreSQL 16 tools available, and run:

```bash
PATH=/usr/lib/postgresql/16/bin:$PATH \
  .venv/bin/python scripts/recovery_drill.py --confirm-isolated
```

The tool refuses remote hosts and requires both explicit configuration and `--confirm-isolated`. It never calls S3 or AWS. Its JSON report records table count, archive size, sequence and empty-target checks; credentials and rows are excluded.

This synthetic drill exercises schema and application restore mechanics. Before release, separately validate the encrypted staging S3 backup, IAM/KMS access, RDS point-in-time recovery, recovery time/data-loss objectives and deployment rollback using the deployment acceptance guide. Those cloud recovery checks have not been performed here.

Primary tool references: [Anchore scan action](https://github.com/anchore/scan-action), [pip-audit](https://github.com/pypa/pip-audit), [Cosign installation](https://github.com/sigstore/cosign-installer), [signature verification](https://docs.sigstore.dev/cosign/verifying/verify/).
