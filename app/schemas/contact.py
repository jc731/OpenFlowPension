import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class MemberContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    member_id: uuid.UUID
    contact_type: str
    value: str
    is_primary: bool
    effective_date: date
    end_date: date | None = None
