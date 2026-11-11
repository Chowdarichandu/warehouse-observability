# EC2 and EKS deployment

This guide describes the supported AWS deployment shape for Pravah. Configure each environment with its own account, network, Airflow and Airbyte endpoints, warehouse, identity provider and secret references. Live connections use only the endpoints and roles supplied to the service.

## Shared setup

1. Build and scan both images from the same Git commit, push them to private ECR, and deploy immutable digest references. The CI build workflow supports this after `AWS_BUILD_ROLE_ARN` is configured. Do not use mutable `latest` tags.
2. Use a private RDS PostgreSQL 16 database with Multi-AZ, encryption, deletion protection, automatic backups and PITR. Restrict its security group to the application/migration/backup roles' hosts or pod security groups. The API has no public port. The web service is behind an internal HTTPS ALB/ACM certificate; allow ingress from the corporate VPN or approved networks.
3. Create a separate Secrets Manager JSON object for each service. Values are string environment variables; JSON arrays/maps inside them must also be strings. Bootstrap with `OBS_CONFIG_SECRET_ID`; the entrypoint obtains temporary credentials from the EC2 instance role, EKS Pod Identity, or IRSA. Do not use static AWS access keys. Secret rotation requires a controlled rollout; services reload secret values on startup.
4. Apply migrations with the migration service/job using a dedicated schema-owner database credential. API/collector/alerter credentials use an `obs_app` role login; Airflow registry access uses `obs_ro`; backup uses a read-only backup role. `005_roles.sql` creates non-login group roles; create your own login roles and grant the appropriate group. RDS master credentials never enter an application service.
5. Configure OIDC and callback `https://console.example.com/api/auth/oidc/callback`, explicit group-role mapping, and a cryptographically random `JWT_SECRET` of at least 32 characters. Live mode rejects the demo signing key, public demo mode, insecure non-local console URLs, and database DSNs without `sslmode=verify-full`. Local password authentication requires the explicit `ALLOW_LOCAL_AUTH_IN_LIVE=true` setting. Database and warehouse connections verify hostnames; the image includes the public AWS RDS trust bundle under `/app/certs/rds-global-bundle.pem`.
6. Start with `LIVE_ACTIONS_ENABLED=false` and `REGISTRY_DAGS_ENABLED=false`. Configure and verify collection before enabling writes. Review the DAG templates and mapping instructions in `airflow/dags/README.md` first.
7. Apply a reviewed tenant/channel/rule YAML with `python -m obs.configure /path/to/live.yaml`. `--check` validates it without touching a database. Copy `config/live.example.yaml`, replace example IDs, and route **every enabled rule** to an owned channel. The example only shows two rules; the other built-in rules must be routed or intentionally disabled.

A minimal API secret includes `DATABASE_URL`, `JWT_SECRET`, `OIDC_CLIENT_SECRET`, `AIRFLOW_READ_TOKEN` (on-demand logs/async retry checks), `AIRFLOW_WRITE_TOKEN`, `AIRBYTE_WRITE_TOKEN`, `WAREHOUSE_URL`, and any onboarding workspace/destination configuration. The collector secret has a read-only Airflow token, read-only Airbyte token/application credentials, read-only warehouse DSN, and its own observation-store login. The alerter secret has its own DB login, the common signing/OIDC validation values, and only its notification provider settings. Each service also receives the common non-secret configuration from `.env.live` or Helm `env`.

The shared Settings validation requires `JWT_SECRET` and OIDC configuration in all live services. Keep the signing secret accessible only to trusted application workloads; network-facing services do not expose it. A migration/backup secret needs its dedicated database login and the same required live configuration, without upstream write credentials.

## EC2

Use an Ubuntu/Amazon Linux host in the VPC with Docker Engine and Compose v2 installed. Keep SSH closed and use SSM Session Manager. Assign an instance role with scoped permissions from `deploy/iam/`; a single Compose host shares the instance role across containers, so use EKS when IAM isolation between services is required. IMDSv2 is required. Container credential access needs an IMDS hop limit of 2; restrict untrusted workloads and inbound traffic on that host.

Clone to `/opt/warehouse-observability`, copy `.env.live.example` to `.env.live`, and replace the public configuration. Set image digests in `/etc/observability/images.env`:

```dotenv
OBS_API_IMAGE=ACCOUNT.dkr.ecr.REGION.amazonaws.com/observability-api@sha256:YOUR_DIGEST
OBS_WEB_IMAGE=ACCOUNT.dkr.ecr.REGION.amazonaws.com/observability-web@sha256:YOUR_DIGEST
OBS_BIND_ADDRESS=10.0.1.10
```

The bind address must be the EC2 private address reached by the ALB. The default is loopback for local reverse-proxy setups. Permit port 8080 only from the ALB security group; do not expose 8000 or the database. Install `deploy/ec2/observability.service` and enable it after an ECR login using the instance role. The service runs the migration to completion, waits for API health, then starts workers/web. `make live` invokes the same live Compose file after `.env.live` exists. Standard `make down` controls the local demo; stop the live stack with `docker compose -f deploy/ec2/compose.yaml down` from the checkout with the image variables loaded.

Use `docker compose -f deploy/ec2/compose.yaml ps` and `/api/health` for readiness; a running container alone is not a successful release. Send stdout to CloudWatch with the CloudWatch agent or an approved container log configuration. The supplied Compose file rotates local logs. Reauthenticate ECR before pulling a release. Back up before migrations. Keep the prior image digests for rollback; database migrations are forward-only, so application rollback must remain compatible with the new schema.

## EKS

Install the AWS Load Balancer Controller and EKS Pod Identity Agent (or configure IRSA). Use one release per namespace; the internal API service is named `api` for nginx proxy resolution. Do not reuse the namespace for another console release.

1. Associate **different** IAM roles with service accounts `obs-api`, `obs-collector`, `obs-alerter`, `obs-migration`, and optionally `obs-backup`. Use Pod Identity associations or the chart's `roleArn` IRSA annotations. The migration service account is a pre-install hook; create its Pod Identity association before installing the release. Do not bind Kubernetes RBAC privileges to these accounts.
2. Copy `deploy/helm/obs-console/values.yaml` to an untracked environment-specific values file. Set image digests, Secrets Manager IDs, common public configuration, VPC CIDRs, ALB host and ACM certificate annotation. Enable ingress once the certificate is set. Private subnets need NAT or VPC endpoints for ECR, Secrets Manager, STS, S3, and notification/OIDC endpoints.
3. Run `helm lint`, render the chart, and review it before installation. Install with `helm upgrade --install obs deploy/helm/obs-console -n observability --create-namespace -f /secure/values.yaml --atomic --wait --timeout 10m`. The pre-install/pre-upgrade migration job must succeed before workloads roll. Use a cluster with network policy enforcement (EKS VPC CNI network policy or equivalent).
4. The chart supplies non-root containers, read-only filesystems, dropped capabilities, resource bounds, topology spreading, API readiness/liveness/startup probes, a disruption budget, graceful shutdown, and a network policy. Review egress CIDRs and ports for your actual source databases. AWS/OIDC/webhook HTTPS egress remains allowed; restrict it further through your egress proxy/VPC controls. Pod Identity's link-local credential endpoint is explicitly allowed; EC2 node metadata is excluded from the general HTTPS rule.
5. Optional scheduled encrypted S3 backups use `backup.enabled=true`, a dedicated secret and role, and an ephemeral work volume. Monitor failed Jobs. The collector and alerter also publish heartbeats checked by readiness probes; leader locks coordinate overlap during rolling updates.

## AWS permissions and services

`deploy/iam/*.example.json` are scoped policy templates: substitute REGION, ACCOUNT, secret ARNs, MWAA environment, SNS topic, verified SES identity, bucket and KMS key. Remove services you do not use. Add `kms:Decrypt` for each service's Secrets Manager customer-managed key when needed. The migration role only needs its secret and DB network access. The Airflow onboarding workers need their own scoped secret/Airbyte/DB access.

MWAA uses `InvokeRestApi` with IAM/SigV4 and Viewer access for collection; operator access is a separately assumed role. Self-hosted Airflow on EC2/EKS uses distinct read/write bearer tokens or BasicAuth credentials from your auth manager or reverse proxy. Set `AIRFLOW_AUTH_METHOD=bearer` with the token variables, or `AIRFLOW_AUTH_METHOD=basic` with separate read and write username/password secret references. API version and DAG IDs are explicit configuration. Test the environment's endpoint length, log access and payload limits, especially with MWAA mapped task URLs. PostgreSQL and Redshift warehouse adapters use catalog estimates; no full-table row counts are issued. Keep an index/sort key on the load-time column to bound freshness queries.

SES requires a verified sender and production access (or verified sandbox recipients). SNS requires confirmed subscriptions. Slack/Teams require the exact webhook host in `NOTIFICATION_ALLOWED_HOSTS`. Email uses TLS-only SMTP or SES. The notification outbox has bounded exponential retries, visible failures, and lease recovery. Delivery is **at least once**: a provider may accept a message immediately before a worker crash, so duplicates remain possible. Acknowledging an alert suppresses future repeat notifications; messages already accepted by a provider cannot be recalled.

## Backup and restore

RDS PITR is the primary recovery mechanism. The optional `python -m obs.backup create` makes a verified `pg_dump` custom archive and uploads it under `observability/` with SSE-KMS. Configure bucket versioning, a retention lifecycle and access logging. No credential is passed as a process argument. For EC2, run the backup command in the API image with a dedicated backup secret/role via your scheduler.

Restore only into an empty, isolated database: set its `DATABASE_URL` in the backup service secret and run `python -m obs.backup restore --key observability/...dump --confirm-empty`. The tool refuses a target with user tables and restores in one transaction. Verify tenant/run counts, migrations, roles and a read-only application walkthrough before cutover. Test restores on a schedule; successful uploads alone are insufficient.

## Release acceptance

Before production, supply and record: 20 sampled staging run comparisons, mapped-task retry isolation, one staging tenant onboarded through initial load, pause/resume registry behavior, each chosen real notification provider, OIDC group/denial/logout/session revocation, EKS/EC2 image and probe checks, an isolated backup restore, and deployment rollback. The repository's local tests use synthetic contract fixtures and do not substitute for this staging evidence.

The optional `deploy/cloudformation/alarms.yaml` monitors unhealthy ALB targets, target 5xx responses, and RDS free storage through an SNS topic. Set the target ALB, target group and database identifiers. Add Container Insights or your cluster's native alarms for unavailable worker replicas and failed backup jobs, so a stopped alerter is detected outside the application.

Dependency scans cover the locked Python environment and the complete npm dependency tree. A scoped npm override pins the TypeScript ESLint parser's `minimatch` dependency to the patched 11.0.1 release; lint/type checks validate that combination. Recheck advisories on every release. CI's image-publishing job is manual, uses GitHub OIDC and records ECR digests/SBOMs; configure its AWS trust policy for this repository's `image-publishing` environment and grant push access only to the two ECR repositories. Publishing images does not deploy them.
