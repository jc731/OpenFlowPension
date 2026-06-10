import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class MemberContactCreate(BaseModel):
    contact_type: str  # e.g. phone, mobile, email
    value: str
    is_primary: bool = False
    effective_date: date
    # When true, end-date the member's active contacts of the same type
    # (replacement); when false, the new contact is added alongside them.
    supersede: bool = False


class MemberContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    member_id: uuid.UUID
    contact_type: str
    value: str
    is_primary: bool
    effective_date: date
    end_date: date | None = None
