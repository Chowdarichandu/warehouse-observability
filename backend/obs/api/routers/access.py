from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from obs.access import ROLE_DESCRIPTIONS, Role, permissions
from obs.auth import current_user
from obs.settings import settings

router = APIRouter(tags=["Workspace access"])


class AccessIdentity(BaseModel):
    email: str
    display_name: str
    provider: Literal["local", "oidc"]


class AccessRole(BaseModel):
    role: Role
    label: str
    description: str


class AccessPermission(BaseModel):
    id: str
    label: str
    description: str
    minimum_role: Role
    roles: list[Role]
    allowed: bool
    enabled: bool
    reason: str


class AccessContext(BaseModel):
    role: Role
    identity: AccessIdentity
    policy_source: Literal["workspace_roles", "oidc_group_mapping"]
    role_assignment_managed: bool
    capabilities: list[str]
    role_capabilities: list[str]
    roles: list[AccessRole]
    permissions: list[AccessPermission]


@router.get("/access", response_model=AccessContext)
def access(user: dict = Depends(current_user)) -> dict:
    config = settings()
    policy = permissions(user["role"], config, user.get("permissions", []))
    return {
        "role": user["role"],
        "identity": {
            "email": user["email"],
            "display_name": user["display_name"] or user["email"],
            "provider": config.auth_provider,
        },
        "policy_source": "oidc_group_mapping"
        if config.auth_provider == "oidc"
        else "workspace_roles",
        "role_assignment_managed": config.auth_provider == "oidc",
        "capabilities": [item["id"] for item in policy if item["enabled"]],
        "role_capabilities": [item["id"] for item in policy if item["allowed"]],
        "roles": ROLE_DESCRIPTIONS,
        "permissions": policy,
    }
