"""add document tables

Revision ID: 90a94f97720e
Revises: 55fb0ada6579
Create Date: 2026-05-06 19:45:02.741837

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '90a94f97720e'
down_revision: Union[str, None] = '55fb0ada6579'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('document_templates',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    sa.Column('slug', sa.String(), nullable=False),
    sa.Column('document_type', sa.String(), nullable=False),
    sa.Column('template_file', sa.String(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('config_value', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('generated_documents',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    sa.Column('template_id', sa.UUID(), nullable=False),
    sa.Column('member_id', sa.UUID(), nullable=True),
    sa.Column('generated_by', sa.UUID(), nullable=True),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.Column('filename', sa.String(), nullable=False),
    sa.Column('status', sa.String(), server_default='generated', nullable=False),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.ForeignKeyConstraint(['template_id'], ['document_templates.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('form_submissions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    sa.Column('template_id', sa.UUID(), nullable=False),
    sa.Column('member_id', sa.UUID(), nullable=False),
    sa.Column('generated_document_id', sa.UUID(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('returned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('return_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.String(), server_default='sent', nullable=False),
    sa.ForeignKeyConstraint(['generated_document_id'], ['generated_documents.id'], ),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.ForeignKeyConstraint(['template_id'], ['document_templates.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('form_submissions')
    op.drop_table('generated_documents')
    op.drop_table('document_templates')
