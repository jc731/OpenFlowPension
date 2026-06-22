"""add beneficiary deceased_date and document_attachments table

Revision ID: f3e9a1c7d854
Revises: c8f912a3bd2e
Create Date: 2026-06-22 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3e9a1c7d854'
down_revision: Union[str, None] = 'c8f912a3bd2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'beneficiaries',
        sa.Column('deceased_date', sa.Date(), nullable=True),
    )

    op.create_table(
        'document_attachments',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('file_name', sa.String(), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('storage_path', sa.Text(), nullable=False),
        sa.Column('uploaded_by', sa.UUID(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_document_attachments_entity', 'document_attachments', ['entity_type', 'entity_id'])


def downgrade() -> None:
    op.drop_index('ix_document_attachments_entity', 'document_attachments')
    op.drop_table('document_attachments')
    op.drop_column('beneficiaries', 'deceased_date')
