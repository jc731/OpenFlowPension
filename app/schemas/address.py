import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


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
