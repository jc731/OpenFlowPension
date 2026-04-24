from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BankAccountCreate(BaseModel):
    bank_name: str
    routing_number: str = Field(min_length=9, max_length=9, pattern=r"^\d{9}$")
    account_number: str = Field(min_length=4)  # plaintext on input — encrypted on write
    account_last_four: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")
    account_type: Literal["checking", "savings"]
    is_primary: bool = False
    effective_date: date
    note: str | None = None


class BankAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    member_id: uuid.UUID
    bank_name: str
    routing_number: str
    account_last_four: str
    account_type: str
    is_primary: bool
    effective_date: date
    end_date: date | None
    note: str | None
    created_at: datetime
    # account_number_encrypted is never exposed
