from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_scope
from app.schemas.benefit import BenefitCalculationRequest, BenefitCalculationResult
from app.services.benefit.calculator import calculate_benefit

router = APIRouter(prefix="/calculate", tags=["benefit"])


@router.post("/benefit", response_model=BenefitCalculationResult, status_code=200,
             dependencies=[Depends(require_scope("benefit:calculate"))])
async def calculate_benefit_endpoint(request: BenefitCalculationRequest) -> BenefitCalculationResult:
    try:
        return calculate_benefit(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
