import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EmployerBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    employer_code: str
    employer_type: str
    active: bool = True


class EmployerCreate(EmployerBase):
    pass


class EmployerRead(EmployerBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
