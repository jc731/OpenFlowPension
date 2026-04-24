import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class EmploymentRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    member_id: uuid.UUID
    employer_id: uuid.UUID
    employment_type: str
    position_title: str | None = None
    department: str | None = None
    hire_date: date
    termination_date: date | None = None
    termination_reason: str | None = None
    percent_time: float
    is_primary: bool
    created_at: datetime
    updated_at: datetime
