from fastapi import APIRouter, Depends

from obs.api.schemas import OnboardProgress, OnboardResume
from obs.auth import fail, require_role
from obs.onboarding.workflow import resume
from obs.settings import settings

router = APIRouter(tags=["Onboarding"])


@router.post("/onboarding/{tenant_id}/resume", response_model=OnboardProgress)
def resume_onboarding(
    tenant_id: str, body: OnboardResume, user: dict = Depends(require_role("operator"))
) -> dict:
    if settings().mode == "live":
        fail(
            503,
            "onboarding_validation_required",
            "Live onboarding requires staging validation before resuming.",
        )
    return resume(tenant_id, user["email"], start_initial=body.start_initial)
