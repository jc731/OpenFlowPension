import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class LeaveTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type_code: str
    type_label: str
    description: str | None = None


class LeaveBalanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employment_id: uuid.UUID
    leave_type_id: uuid.UUID
    balance_date: date
    balance_hours: float
    source: str | None = None
    note: str | None = None
