import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.schemas.billing import (
    DeficiencyCalcRequest,
    DeficiencyCalcResult,
    DeficiencyInvoiceCreate,
    InvoicePaymentCreate,
    InvoicePaymentRead,
    InvoiceRead,
    RateCreate,
    RateRead,
    SupplementalInvoiceCreate,
    VoidInvoiceRequest,
)
from app.services import billing_service

router = APIRouter(tags=["billing"])

_ADMIN = Depends(require_scope("admin"))


# ── Rates ──────────────────────────────────────────────────────────────────────

@router.post("/billing/rates", response_model=RateRead, status_code=201,
             dependencies=[_ADMIN])
async def create_rate(
    body: RateCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    created_by = uuid.UUID(principal["id"]) if principal["id"] not in ("admin", "dev-admin") else None
    async with session.begin():
        rate = await billing_service.create_rate(
            employee_rate=body.employee_rate,
            employer_rate=body.employer_rate,
            effective_date=body.effective_date,
            session=session,
            employer_id=body.employer_id,
            employment_type=body.employment_type,
            end_date=body.end_date,
            note=body.note,
            created_by=created_by,
        )
        return RateRead.model_validate(rate)


@router.get("/billing/rates", response_model=list[RateRead],
            dependencies=[Depends(require_scope("admin", "member:read"))])
async def list_rates(
    employer_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        rates = await billing_service.list_rates(session, employer_id=employer_id)
        return [RateRead.model_validate(r) for r in rates]


# ── Deficiency calc (preview — no DB write) ────────────────────────────────────

@router.post("/employers/{employer_id}/billing/deficiency-calc",
             response_model=DeficiencyCalcResult,
             dependencies=[Depends(require_scope("admin"))])
async def preview_deficiency(
    employer_id: uuid.UUID,
    body: DeficiencyCalcRequest,
    session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        try:
            result = await billing_service.calculate_deficiency(
                body.payroll_report_ids, employer_id, session
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return result


# ── Invoice creation ───────────────────────────────────────────────────────────

@router.post("/employers/{employer_id}/billing/invoices/deficiency",
             response_model=InvoiceRead, status_code=201)
async def create_deficiency_invoice(
    employer_id: uuid.UUID,
    body: DeficiencyInvoiceCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    created_by = uuid.UUID(principal["id"]) if principal["id"] not in ("admin", "dev-admin") else None
    async with session.begin():
        try:
            invoice = await billing_service.create_deficiency_invoice(
                employer_id=employer_id,
                payroll_report_ids=body.payroll_report_ids,
                due_date=body.due_date,
                session=session,
                note=body.note,
                created_by=created_by,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        await session.refresh(invoice, ["payments"])
        return InvoiceRead.model_validate(invoice)


@router.post("/employers/{employer_id}/billing/invoices/supplemental",
             response_model=InvoiceRead, status_code=201)
async def create_supplemental_invoice(
    employer_id: uuid.UUID,
    body: SupplementalInvoiceCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    created_by = uuid.UUID(principal["id"]) if principal["id"] not in ("admin", "dev-admin") else None
    async with session.begin():
        invoice = await billing_service.create_supplemental_invoice(
            employer_id=employer_id,
            amount_due=body.amount_due,
            due_date=body.due_date,
            line_items=body.line_items,
            session=session,
            note=body.note,
            created_by=created_by,
        )
        await session.refresh(invoice, ["payments"])
        return InvoiceRead.model_validate(invoice)


# ── Invoice queries ────────────────────────────────────────────────────────────

@router.get("/employers/{employer_id}/billing/invoices",
            response_model=list[InvoiceRead],
            dependencies=[Depends(require_scope("admin", "member:read"))])
async def list_invoices(
    employer_id: uuid.UUID,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        invoices = await billing_service.list_invoices(employer_id, session, status=status)
        return [InvoiceRead.model_validate(inv) for inv in invoices]


@router.get("/billing/invoices/{invoice_id}", response_model=InvoiceRead,
            dependencies=[Depends(require_scope("admin", "member:read"))])
async def get_invoice(
    invoice_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        invoice = await billing_service.get_invoice(invoice_id, session)
        if invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found")
        await session.refresh(invoice, ["payments"])
        return InvoiceRead.model_validate(invoice)


# ── Invoice lifecycle ──────────────────────────────────────────────────────────

@router.post("/billing/invoices/{invoice_id}/issue", response_model=InvoiceRead,
             dependencies=[Depends(require_scope("admin"))])
async def issue_invoice(
    invoice_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    async with session.begin():
        invoice = await billing_service.get_invoice(invoice_id, session)
        if invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found")
        try:
            invoice = await billing_service.issue_invoice(invoice, session)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        await session.refresh(invoice, ["payments"])
        return InvoiceRead.model_validate(invoice)


@router.post("/billing/invoices/{invoice_id}/void", response_model=InvoiceRead,
             dependencies=[Depends(require_scope("admin"))])
async def void_invoice(
    invoice_id: uuid.UUID,
    body: VoidInvoiceRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    voided_by = uuid.UUID(principal["id"]) if principal["id"] not in ("admin", "dev-admin") else None
    async with session.begin():
        invoice = await billing_service.get_invoice(invoice_id, session)
        if invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found")
        try:
            invoice = await billing_service.void_invoice(invoice, body.void_reason, session, voided_by=voided_by)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        await session.refresh(invoice, ["payments"])
        return InvoiceRead.model_validate(invoice)


# ── Payments ───────────────────────────────────────────────────────────────────

@router.post("/billing/invoices/{invoice_id}/payments",
             response_model=InvoicePaymentRead, status_code=201)
async def record_payment(
    invoice_id: uuid.UUID,
    body: InvoicePaymentCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("admin")),
):
    received_by = uuid.UUID(principal["id"]) if principal["id"] not in ("admin", "dev-admin") else None
    async with session.begin():
        invoice = await billing_service.get_invoice(invoice_id, session)
        if invoice is None:
            raise HTTPException(status_code=404, detail="Invoice not found")
        try:
            payment = await billing_service.record_payment(
                invoice=invoice,
                amount=body.amount,
                payment_date=body.payment_date,
                payment_method=body.payment_method,
                session=session,
                reference_number=body.reference_number,
                received_by=received_by,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return InvoicePaymentRead.model_validate(payment)
