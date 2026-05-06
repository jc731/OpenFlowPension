from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentTemplateCreate(BaseModel):
    slug: str
    document_type: str
    template_file: str
    description: str | None = None
    config_value: dict = {}


class DocumentTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    document_type: str
    template_file: str
    description: str | None
    config_value: dict
    active: bool
    created_at: datetime


class GenerateDocumentRequest(BaseModel):
    slug: str
    member_id: uuid.UUID
    params: dict[str, Any] = {}


class GeneratedDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID
    member_id: uuid.UUID | None
    generated_by: uuid.UUID | None
    params: dict
    filename: str
    status: str
    created_at: datetime


class FormSubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID
    member_id: uuid.UUID
    generated_document_id: uuid.UUID | None
    sent_at: datetime | None
    returned_at: datetime | None
    status: str
    created_at: datetime
