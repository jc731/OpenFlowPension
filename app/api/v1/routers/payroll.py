import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_scope
from app.database import get_session
from app.schemas.payroll import PayrollReportCreate, PayrollReportRead
from app.services import payroll_service

router = APIRouter(tags=["payroll"])


@router.get("/payroll-reports", response_model=list[PayrollReportRead],
            dependencies=[Depends(require_scope("member:read", "payroll:write"))])
async def list_all_payroll_reports(
    employer_id: uuid.UUID | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    """List payroll reports across all employers. Rows not included — fetch individual report for detail."""
    return await payroll_service.list_all_payroll_reports(session, employer_id=employer_id, limit=limit)


@router.get("/employers/{employer_id}/payroll-reports", response_model=list[PayrollReportRead],
            dependencies=[Depends(require_scope("member:read", "payroll:write"))])
async def list_payroll_reports(
    employer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    return await payroll_service.list_payroll_reports(employer_id, session)


@router.post("/employers/{employer_id}/payroll-reports", response_model=PayrollReportRead, status_code=201)
async def ingest_json(
    employer_id: uuid.UUID,
    data: PayrollReportCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("payroll:write")),
):
    submitted_by = (
        uuid.UUID(principal["id"]) if principal["id"] not in ("admin", "dev-admin") else None
    )
    async with session.begin():
        return await payroll_service.ingest_json(employer_id, data, session, submitted_by=submitted_by)


@router.post("/employers/{employer_id}/payroll-reports/upload", response_model=PayrollReportRead, status_code=201)
async def upload_csv(
    employer_id: uuid.UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_scope("payroll:write")),
):
    submitted_by = (
        uuid.UUID(principal["id"]) if principal["id"] not in ("admin", "dev-admin") else None
    )
    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded")
    try:
        async with session.begin():
            return await payroll_service.ingest_csv(
                employer_id, csv_text, file.filename or "upload.csv", session, submitted_by=submitted_by
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/payroll-reports/{report_id}", response_model=PayrollReportRead,
            dependencies=[Depends(require_scope("member:read", "payroll:write"))])
async def get_payroll_report(
    report_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    report = await payroll_service.get_payroll_report(report_id, session)
    if not report:
        raise HTTPException(status_code=404, detail="Payroll report not found")
    return report
