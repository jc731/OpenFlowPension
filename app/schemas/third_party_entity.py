from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


EntityType = Literal["disbursement_unit", "union", "insurance_carrier", "court", "other"]
PaymentMethod = Literal["ach", "check", "wire", "other"]


class ThirdPartyEntityCreate(BaseModel):
    name: str = Field(min_length=1)
    entity_type: EntityType = "other"
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = Field(default=None, max_length=2)
    zip_code: str | None = Field(default=None, max_length=10)
    phone: str | None = None
    email: str | None = None
    ein: str | None = None
    bank_routing_number: str | None = Field(default=None, min_length=9, max_length=9)
    bank_account_number: str | None = None  # plaintext at intake; stored encrypted
    payment_method: PaymentMethod | None = None
    notes: str | None = None


class ThirdPartyEntityUpdate(BaseModel):
    name: str | None = None
    entity_type: EntityType | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = Field(default=None, max_length=2)
    zip_code: str | None = Field(default=None, max_length=10)
    phone: str | None = None
    email: str | None = None
    ein: str | None = None
    payment_method: PaymentMethod | None = None
    notes: str | None = None


class ThirdPartyEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    entity_type: str
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    phone: str | None
    email: str | None
    ein: str | None
    bank_routing_number: str | None
    bank_account_last_four: str | None  # never expose encrypted field
    payment_method: str | None
    notes: str | None
    active: bool
    created_at: datetime
    updated_at: datetime
