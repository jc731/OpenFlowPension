import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ServiceCreditEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    member_id: uuid.UUID
    employment_id: uuid.UUID | None = None
    entry_type: str
    credit_days: float
    credit_years: float | None = None
    period_start: date | None = None
    period_end: date | None = None
    accrual_rule_config_id: uuid.UUID | None = None
    note: str | None = None
    voided_at: datetime | None = None
    void_reason: str | None = None
    created_at: datetime
