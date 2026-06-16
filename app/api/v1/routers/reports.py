"""Read-only report endpoints.

All endpoints require admin scope. They return typed JSON envelopes that the
frontend ReportViewer consumes. CSV export is handled client-side.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.database import get_session
from app.schemas.reports import (
    AnnuitantReport,
    ContributionReconciliationReport,
    DelinquencyReport,
    MembershipCountReport,
)
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "/contribution-reconciliation",
    response_model=ContributionReconciliationReport,
    dependencies=[Depends(require_scope("admin"))],
)
async def contribution_reconciliation(
    period_start: date = Query(..., description="Start of the contribution period (inclusive)"),
    period_end: date = Query(..., description="End of the contribution period (inclusive)"),
    employer_id: uuid.UUID | None = Query(None, description="Filter to a single employer"),
    session: AsyncSession = Depends(get_session),
):
    return await report_service.contribution_reconciliation(
        period_start, period_end, session, employer_id=employer_id
    )


@router.get(
    "/delinquency",
    response_model=DelinquencyReport,
    dependencies=[Depends(require_scope("admin"))],
)
async def delinquency(
    as_of: date = Query(default_factory=date.today, description="Report date — invoices past due as of this date"),
    session: AsyncSession = Depends(get_session),
):
    return await report_service.delinquency(as_of, session)


@router.get(
    "/membership-counts",
    response_model=MembershipCountReport,
    dependencies=[Depends(require_scope("admin"))],
)
async def membership_counts(
    session: AsyncSession = Depends(get_session),
):
    return await report_service.membership_counts(session)


@router.get(
    "/annuitants",
    response_model=AnnuitantReport,
    dependencies=[Depends(require_scope("admin"))],
)
async def annuitants(
    session: AsyncSession = Depends(get_session),
):
    return await report_service.annuitants(session)
