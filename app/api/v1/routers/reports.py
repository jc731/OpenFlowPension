"""Read-only report endpoints.

All endpoints require admin scope. They return typed JSON envelopes that the
frontend ReportViewer consumes. CSV export is handled client-side.
1099-R (RP05) returns json; pdf/pub1220/csv formats return 501 until implemented.
"""

import csv
import io
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.database import get_session
from app.schemas.reports import (
    AnnuitantReport,
    ContributionReconciliationReport,
    DelinquencyReport,
    Form1099RReport,
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


@router.get(
    "/1099r",
    response_model=Form1099RReport,
    dependencies=[Depends(require_scope("admin"))],
)
async def form_1099r(
    tax_year: int = Query(..., description="Calendar year (e.g. 2025)"),
    format: str = Query("json", description="json | csv | pdf | pub1220"),
    session: AsyncSession = Depends(get_session),
):
    if format not in ("json", "csv", "pdf"):
        raise HTTPException(
            status_code=501,
            detail=f"1099-R format '{format}' is not yet implemented.",
        )
    if format == "pdf":
        pdf_bytes = await report_service.render_1099r_pdf(tax_year, session)
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=1099r_{tax_year}.pdf"},
        )
    report = await report_service.get_1099r_data(tax_year, session)
    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "member_id", "member_number", "last_name", "first_name",
            "ssn_last_four", "gross_distributions", "taxable_amount",
            "federal_tax_withheld", "state_tax_withheld", "distribution_code",
            "payer_name", "payer_ein",
        ])
        writer.writeheader()
        for r in report.rows:
            writer.writerow({
                "member_id": str(r.member_id),
                "member_number": r.member_number,
                "last_name": r.last_name,
                "first_name": r.first_name,
                "ssn_last_four": r.ssn_last_four,
                "gross_distributions": str(r.gross_distributions),
                "taxable_amount": str(r.taxable_amount),
                "federal_tax_withheld": str(r.federal_tax_withheld),
                "state_tax_withheld": str(r.state_tax_withheld),
                "distribution_code": r.distribution_code,
                "payer_name": r.payer_name,
                "payer_ein": r.payer_ein or "",
            })
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=1099r_{tax_year}.csv"},
        )
    return report
