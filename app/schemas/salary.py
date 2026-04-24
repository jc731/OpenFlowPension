import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class SalaryHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employment_id: uuid.UUID
    effective_date: date
    end_date: date | None = None
    annual_salary: float
    salary_type: str
    change_reason: str | None = None
