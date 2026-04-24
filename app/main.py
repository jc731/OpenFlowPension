from fastapi import FastAPI

import app.models  # noqa: F401 — registers all mappers before first request
from app.api.v1.routers.bank_accounts import router as bank_accounts_router
from app.api.v1.routers.benefit import router as benefit_router
from app.api.v1.routers.employers import router as employers_router
from app.api.v1.routers.employment import router as employment_router
from app.api.v1.routers.members import router as members_router
from app.api.v1.routers.payments import router as payments_router
from app.api.v1.routers.payroll import router as payroll_router

app = FastAPI(
    title="OpenFlow Pension API",
    version="0.1.0",
    description="Open source pension administration platform",
)

app.include_router(members_router, prefix="/api/v1")
app.include_router(employers_router, prefix="/api/v1")
app.include_router(employment_router, prefix="/api/v1")
app.include_router(benefit_router, prefix="/api/v1")
app.include_router(bank_accounts_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(payroll_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
