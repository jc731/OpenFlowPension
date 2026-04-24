import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator


class BeneficiaryCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    first_name: str
    last_name: str
    date_of_birth: date | None = None
    relationship: str
    beneficiary_type: str
    share_percent: float | None = None
    effective_date: date

    @field_validator("share_percent")
    @classmethod
    def share_percent_range(cls, v: float | None) -> float | None:
        if v is not None and not (0 < v <= 100):
            raise ValueError("share_percent must be between 0 (exclusive) and 100 (inclusive)")
        return v


class BeneficiaryRead(BeneficiaryCreate):
    id: uuid.UUID
    member_id: uuid.UUID
    end_date: date | None = None
