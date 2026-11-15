from fastapi import APIRouter, Depends

from obs.api.schemas import OnboardProgress, OnboardResume
from obs.auth import fail, require_role
from obs.onboarding.workflow import resume
from obs.settings import settings

router = APIRouter(tags=["Onboarding"])


@router.post("/onboarding/{tenant_id}/resume", response_model=OnboardProgress)
def resume_onboarding(
    tenant_id: str,
    body: OnboardResume,
    user: dict = Depends(require_role("operator", "manage_tenants")),
) -> dict:
    if settings().mode == "live":
        fail(
            503,
            "onboarding_validation_required",
            "Live onboarding is turned off. An admin can turn it on after the tenant isolation check passes.",
        )
    return resume(tenant_id, user["email"], start_initial=body.start_initial)
