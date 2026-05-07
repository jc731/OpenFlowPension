import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_scope
from app.schemas.service_purchase import (
    ApprovePurchaseClaimRequest,
    CancelPurchaseClaimRequest,
    ServicePurchaseClaimCreate,
    ServicePurchaseClaimRead,
    ServicePurchasePaymentCreate,
    ServicePurchasePaymentRead,
    ServicePurchaseQuoteRequest,
    ServicePurchaseQuoteResult,
)
from app.services import service_purchase_service as svc

router = APIRouter(tags=["service-purchase"])


def _claim_or_404(claim, claim_id: uuid.UUID):
    if not claim:
        raise HTTPException(status_code=404, detail=f"Service purchase claim {claim_id} not found")
    return claim


@router.post("/members/{member_id}/service-purchase/quote", response_model=ServicePurchaseQuoteResult)
async def quote_service_purchase(
    member_id: uuid.UUID,
    req: ServicePurchaseQuoteRequest,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Stateless cost estimate. Does not create any records."""
    require_scope(principal, "member:read")
    try:
        return await svc.quote(member_id, req, session)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/members/{member_id}/service-purchase/claims", response_model=ServicePurchaseClaimRead, status_code=201)
async def create_claim(
    member_id: uuid.UUID,
    data: ServicePurchaseClaimCreate,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Create a purchase claim (status=draft). Runs the cost calculation and persists the snapshot."""
    require_scope(principal, "member:write")
    created_by = uuid.UUID(principal["id"]) if principal.get("id") else None
    try:
        claim = await svc.create_claim(member_id, data, session, created_by=created_by)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await session.commit()
    await session.refresh(claim)
    return claim


@router.get("/members/{member_id}/service-purchase/claims", response_model=list[ServicePurchaseClaimRead])
async def list_claims(
    member_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    require_scope(principal, "member:read")
    return await svc.list_claims(member_id, session)


@router.get("/service-purchase/claims/{claim_id}", response_model=ServicePurchaseClaimRead)
async def get_claim(
    claim_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    require_scope(principal, "member:read")
    claim = _claim_or_404(await svc.get_claim(claim_id, session), claim_id)
    return claim


@router.post("/service-purchase/claims/{claim_id}/submit", response_model=ServicePurchaseClaimRead)
async def submit_claim(
    claim_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Transition draft → pending_approval."""
    require_scope(principal, "member:write")
    claim = _claim_or_404(await svc.get_claim(claim_id, session), claim_id)
    try:
        claim = await svc.submit_claim(claim, session)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await session.commit()
    return claim


@router.post("/service-purchase/claims/{claim_id}/approve", response_model=ServicePurchaseClaimRead)
async def approve_claim(
    claim_id: uuid.UUID,
    req: ApprovePurchaseClaimRequest = ApprovePurchaseClaimRequest(),
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Transition pending_approval → approved. Grants credit immediately if credit_grant_on='approval'."""
    require_scope(principal, "member:write")
    approver_id = uuid.UUID(principal["id"]) if principal.get("id") else uuid.uuid4()
    claim = _claim_or_404(await svc.get_claim(claim_id, session), claim_id)
    try:
        claim = await svc.approve_claim(claim, approver_id, session, notes=req.notes)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await session.commit()
    return claim


@router.post("/service-purchase/claims/{claim_id}/cancel", response_model=ServicePurchaseClaimRead)
async def cancel_claim(
    claim_id: uuid.UUID,
    req: CancelPurchaseClaimRequest,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    require_scope(principal, "member:write")
    claim = _claim_or_404(await svc.get_claim(claim_id, session), claim_id)
    try:
        claim = await svc.cancel_claim(claim, req.cancel_reason, session)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await session.commit()
    return claim


@router.post(
    "/service-purchase/claims/{claim_id}/payments",
    response_model=ServicePurchasePaymentRead,
    status_code=201,
)
async def record_payment(
    claim_id: uuid.UUID,
    data: ServicePurchasePaymentCreate,
    session: AsyncSession = Depends(get_db),
    principal=Depends(get_current_user),
):
    """Record a payment. Auto-completes the claim and grants service credit when fully paid."""
    require_scope(principal, "member:write")
    received_by = uuid.UUID(principal["id"]) if principal.get("id") else None
    claim = _claim_or_404(await svc.get_claim(claim_id, session), claim_id)
    try:
        payment = await svc.record_payment(claim, data, session, received_by=received_by)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await session.commit()
    return payment
