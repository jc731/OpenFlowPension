import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class MemberBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    member_number: str
    first_name: str
    middle_name: str | None = None
    last_name: str
    suffix: str | None = None
    date_of_birth: date
    gender: str | None = None
    member_status: str = "active"
    status_date: date | None = None
    plan_tier_id: uuid.UUID | None = None
    plan_type_id: uuid.UUID | None = None
    plan_choice_date: date | None = None
    plan_choice_locked: bool = False
    certification_date: date | None = None


class MemberCreate(MemberBase):
    ssn: str

    @field_validator("ssn")
    @classmethod
    def ssn_format(cls, v: str) -> str:
        digits = v.replace("-", "").replace(" ", "")
        if not digits.isdigit() or len(digits) != 9:
            raise ValueError("SSN must be 9 digits")
        return digits


class MemberRead(MemberBase):
    id: uuid.UUID
    ssn_last_four: str
    # ssn_encrypted is intentionally absent — never expose ciphertext in API responses
    created_at: datetime
    updated_at: datetime


class MemberImportRowError(BaseModel):
    row: int  # 1-based CSV line number; the header is line 1
    member_number: str | None = None
    error: str


class MemberImportResult(BaseModel):
    total_rows: int
    created_count: int
    error_count: int
    errors: list[MemberImportRowError]
