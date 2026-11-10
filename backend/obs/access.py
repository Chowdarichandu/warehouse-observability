"""Workspace capabilities derived from trusted, server-resolved roles.

This is the application policy, not an external IAM client. OIDC identity validation
and group mapping remain in obs.oidc; the database role is authoritative per request.
"""

from dataclasses import dataclass
from typing import Literal

from obs.settings import Settings

Role = Literal["viewer", "operator", "admin"]
ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}
ROLE_DESCRIPTIONS = (
    {
        "role": "viewer",
        "label": "Viewer",
        "description": "Inspect health, investigate runs and save personal views.",
    },
    {
        "role": "operator",
        "label": "Operator",
        "description": "Respond to alerts, retry pipelines and onboard tenants.",
    },
    {
        "role": "admin",
        "label": "Admin",
        "description": "Configure the workspace, manage access and review audit history.",
    },
)


def role_at_least(actual: str, required: str) -> bool:
    """Unknown roles fail closed; only the server's canonical role names carry access."""
    return (
        actual in ROLE_RANK and required in ROLE_RANK and ROLE_RANK[actual] >= ROLE_RANK[required]
    )


@dataclass(frozen=True)
class Capability:
    id: str
    label: str
    description: str
    minimum_role: Role
    gate: str = ""


CAPABILITIES = (
    Capability(
        "workspace.read",
        "View and investigate",
        "Read tenant health, runs, logs, dependencies, quality results and onboarding progress.",
        "viewer",
    ),
    Capability(
        "investigations.save",
        "Save personal views",
        "Save and remove your own investigation filters.",
        "viewer",
    ),
    Capability(
        "pipelines.retry",
        "Retry pipelines",
        "Request a reviewed retry of a failed pipeline run.",
        "operator",
        "live_actions",
    ),
    Capability(
        "alerts.respond",
        "Respond to alerts",
        "Acknowledge alerts and record their resolution.",
        "operator",
    ),
    Capability(
        "onboarding.start",
        "Onboard tenants",
        "Validate source configuration and start tenant onboarding.",
        "operator",
        "registry",
    ),
    Capability(
        "tenants.configure",
        "Configure tenants",
        "Change freshness SLAs and tenant lifecycle settings.",
        "admin",
        "live_actions",
    ),
    Capability(
        "alerts.configure",
        "Configure alerts",
        "Edit built-in alert rules and test notification channels.",
        "admin",
    ),
    Capability(
        "quality.run",
        "Run quality checks",
        "Evaluate enabled bounded data-quality checks.",
        "operator",
        "quality_run",
    ),
    Capability(
        "quality.configure",
        "Configure quality checks",
        "Create, edit and enable built-in data-quality checks.",
        "admin",
        "live_actions",
    ),
    Capability(
        "audit.read",
        "Read audit history",
        "Review workspace actions, users and notification delivery history.",
        "admin",
    ),
    Capability(
        "operations.reconcile",
        "Reconcile operations",
        "Record evidence for an uncertain upstream operation outcome.",
        "admin",
    ),
    Capability(
        "access.assign_roles",
        "Assign workspace roles",
        "Manage local workspace role assignments; SSO roles come from identity-provider groups.",
        "admin",
        "local_roles",
    ),
    Capability(
        "access.revoke_sessions",
        "Revoke user sessions",
        "End existing sessions for a workspace user.",
        "admin",
    ),
)


def disabled_reason(capability: Capability, config: Settings) -> str:
    if capability.gate == "local_roles" and config.auth_provider == "oidc":
        return "Role assignments are managed through your identity provider groups."
    if config.mode == "live":
        if capability.id == "onboarding.start":
            return (
                "Live onboarding requires staging validation of tenant isolation and DAG recovery."
            )
        if (
            capability.gate in {"live_actions", "registry", "quality_run"}
            and not config.live_actions_enabled
        ):
            return "Live actions are disabled until the environment is reviewed."
        if capability.gate == "registry" and not config.registry_dags_enabled:
            return "Tenant onboarding requires the reviewed registry-driven DAGs."
        if capability.gate == "quality_run" and not config.quality_enabled:
            return "Live warehouse quality checks have not been enabled."
    return ""


def permissions(role: str, config: Settings) -> list[dict]:
    result = []
    for capability in CAPABILITIES:
        allowed = role_at_least(role, capability.minimum_role)
        reason = (
            disabled_reason(capability, config)
            if allowed
            else f"Requires the {capability.minimum_role.title()} role."
        )
        result.append(
            {
                "id": capability.id,
                "label": capability.label,
                "description": capability.description,
                "minimum_role": capability.minimum_role,
                "roles": [
                    value for value in ROLE_RANK if role_at_least(value, capability.minimum_role)
                ],
                "allowed": allowed,
                "enabled": allowed and not reason,
                "reason": reason,
            }
        )
    return result
