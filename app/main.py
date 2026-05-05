from fastapi import FastAPI

import app.models  # noqa: F401 — registers all mappers before first request
from app.api.v1.routers.bank_accounts import router as bank_accounts_router
from app.api.v1.routers.benefit import router as benefit_router
from app.api.v1.routers.employers import router as employers_router
from app.api.v1.routers.employment import router as employment_router
from app.api.v1.routers.members import router as members_router
from app.api.v1.routers.payments import router as payments_router
from app.api.v1.routers.payroll import router as payroll_router
from app.api.v1.routers.contracts import router as contracts_router
from app.api.v1.routers.beneficiaries import router as beneficiaries_router
from app.api.v1.routers.survivor import router as survivor_router
from app.api.v1.routers.retirement import router as retirement_router
from app.api.v1.routers.api_keys import router as api_keys_router
from app.api.v1.routers.third_party_entities import router as third_party_entities_router
from app.api.v1.routers.net_pay import router as net_pay_router

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
app.include_router(contracts_router, prefix="/api/v1")
app.include_router(beneficiaries_router, prefix="/api/v1")
app.include_router(survivor_router, prefix="/api/v1")
app.include_router(retirement_router, prefix="/api/v1")
app.include_router(api_keys_router, prefix="/api/v1")
app.include_router(third_party_entities_router, prefix="/api/v1")
app.include_router(net_pay_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
