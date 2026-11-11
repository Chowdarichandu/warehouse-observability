from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from obs.access import (
    ROLE_DESCRIPTIONS,
    ROLE_RANK,
    Role,
    module_access,
    module_is_allowed,
    permissions,
)
from obs.audit import audit
from obs.auth import current_user, fail, require_role
from obs.db import connection
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
    modules: list["ModuleAccess"]


class ModuleAccess(BaseModel):
    module_id: str
    display_name: str
    enabled: bool
    access: Literal["admin", "granted"]


class ModuleOverrideIn(BaseModel):
    effect: Literal["grant", "revoke"]


class ModuleGrantOut(BaseModel):
    message: str
    module_id: str
    effect: Literal["grant", "revoke"]


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
        "modules": module_access(user),
    }


@router.put("/access/roles/{role_name}/modules/{module_id}", response_model=ModuleGrantOut)
def grant_role_module(
    role_name: str,
    module_id: str,
    user: dict = Depends(require_role("admin", "manage_users")),
) -> dict:
    """Grant a product area to a reusable workspace role."""
    if role_name in ROLE_RANK:
        fail(
            422,
            "built_in_role",
            "Assign modules to a custom role or use a per-user override for built-in roles.",
        )
    with connection() as conn:
        role = conn.execute(
            "SELECT 1 FROM obs.roles WHERE name=%s",
            (role_name,),
        ).fetchone()
        module = conn.execute(
            "SELECT module_id FROM obs.modules WHERE module_id=%s", (module_id,)
        ).fetchone()
        if not role:
            fail(404, "role_not_found", "That role does not exist.")
        if not module:
            fail(404, "module_not_found", "That module does not exist.")
        conn.execute(
            """INSERT INTO obs.role_modules(role_name,module_id,granted_by)
            VALUES(%s,%s,%s)
            ON CONFLICT(role_name,module_id) DO UPDATE SET granted_by=EXCLUDED.granted_by,granted_at=now()""",
            (role_name, module_id, user["email"]),
        )
        audit(conn, user["email"], "grant_role_module", f"{role_name}:{module_id}")
    return {
        "message": f"{module_id} access granted to {role_name}.",
        "module_id": module_id,
        "effect": "grant",
    }


@router.delete("/access/roles/{role_name}/modules/{module_id}", response_model=ModuleGrantOut)
def revoke_role_module(
    role_name: str,
    module_id: str,
    user: dict = Depends(require_role("admin", "manage_users")),
) -> dict:
    """Remove a product-area grant from a reusable workspace role."""
    if role_name in ROLE_RANK:
        fail(
            422,
            "built_in_role",
            "Built-in role access is managed through per-user overrides.",
        )
    with connection() as conn:
        role = conn.execute(
            "SELECT 1 FROM obs.roles WHERE name=%s",
            (role_name,),
        ).fetchone()
        module = conn.execute(
            "SELECT module_id FROM obs.modules WHERE module_id=%s", (module_id,)
        ).fetchone()
        if not role:
            fail(404, "role_not_found", "That role does not exist.")
        if not module:
            fail(404, "module_not_found", "That module does not exist.")
        conn.execute(
            "DELETE FROM obs.role_modules WHERE role_name=%s AND module_id=%s",
            (role_name, module_id),
        )
        audit(conn, user["email"], "revoke_role_module", f"{role_name}:{module_id}")
    return {
        "message": f"{module_id} access revoked from {role_name}.",
        "module_id": module_id,
        "effect": "revoke",
    }


@router.put("/access/users/{id}/modules/{module_id}", response_model=ModuleGrantOut)
def set_user_module(
    id: int,
    module_id: str,
    data: ModuleOverrideIn,
    user: dict = Depends(require_role("admin", "manage_users")),
) -> dict:
    """Apply a per-user module override with an append-only audit event."""
    if id == user.get("user_id"):
        fail(409, "self_permissions", "You cannot change your own module access.")
    with connection() as conn:
        if not conn.execute("SELECT 1 FROM obs.users WHERE user_id=%s", (id,)).fetchone():
            fail(404, "user_not_found", "User not found.")
        if not conn.execute(
            "SELECT 1 FROM obs.modules WHERE module_id=%s", (module_id,)
        ).fetchone():
            fail(404, "module_not_found", "That module does not exist.")
        conn.execute(
            """INSERT INTO obs.user_module_overrides(user_id,module_id,effect,updated_by)
            VALUES(%s,%s,%s,%s)
            ON CONFLICT(user_id,module_id) DO UPDATE
            SET effect=EXCLUDED.effect,updated_by=EXCLUDED.updated_by,updated_at=now()""",
            (id, module_id, data.effect, user["email"]),
        )
        audit(conn, user["email"], "set_user_module", f"{id}:{module_id}", {"effect": data.effect})
    return {
        "message": f"{module_id} access {data.effect}ed for user {id}.",
        "module_id": module_id,
        "effect": data.effect,
    }


def require_module(module_id: str):
    def dependency(user: dict = Depends(current_user)) -> dict:
        if not module_is_allowed(module_id, user):
            fail(403, "module_forbidden", "Your account cannot access this product module.")
        return user

    return dependency
