import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class PlanTierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tier_code: str
    tier_label: str
    effective_date: date
    closed_date: date | None = None


class PlanTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    plan_code: str
    plan_label: str


class SystemConfigurationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    config_key: str
    config_value: dict
    effective_date: date
    superseded_date: date | None = None
    note: str | None = None
    created_at: datetime
