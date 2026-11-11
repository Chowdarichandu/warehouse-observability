# Security

## Identity and access

Live deployments use OIDC group mappings by default. Local accounts use Argon2id password hashes. Sessions are server-side, revocable and protected by Secure, HttpOnly cookies and CSRF checks. The API enforces role permissions; hiding a control in the console does not grant or deny access by itself.

See [access](access.md) for the role and permission behavior.

## Credentials and data

- Store integration credentials in AWS Secrets Manager or an approved secret store. Configuration accepts references; credentials do not belong in tenant records or browser code.
- Keep read and write credentials separate. The collector uses read-only upstream access; operator writes are disabled until explicitly configured.
- Redact pipeline error and log text before storage and before returning it from the API.
- Keep PostgreSQL private and restrict outbound network access to configured services.
- Keep API, collector, worker and migration roles separate in EKS where workload isolation is required.

## Verification

CI scans the repository for secrets, audits locked dependencies and scans container images. Review the [release checklist](release-checklist.md) before promoting a build. Do not put credentials, tokens, customer names or real account identifiers in fixtures, screenshots or documentation.
