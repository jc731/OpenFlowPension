import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator


class MemberAddressCreate(BaseModel):
    address_type: str = "mailing"
    line1: str
    line2: str | None = None
    city: str
    state: str
    zip: str
    country: str = "US"
    effective_date: date

    @field_validator("state")
    @classmethod
    def state_two_letter(cls, v: str) -> str:
        if len(v) != 2 or not v.isalpha():
            raise ValueError("state must be a 2-letter code")
        return v.upper()


class MemberAddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    member_id: uuid.UUID
    address_type: str
    line1: str
    line2: str | None = None
    city: str
    state: str
    zip: str
    country: str
    effective_date: date
    end_date: date | None = None
