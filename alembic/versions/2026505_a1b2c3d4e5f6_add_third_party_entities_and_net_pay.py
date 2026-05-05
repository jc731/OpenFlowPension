"""add third_party_entities and deduction_order fk

Revision ID: a1b2c3d4e5f6
Revises: 1948648992bf
Create Date: 2026-05-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '1948648992bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'third_party_entities',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), server_default='other', nullable=False),
        sa.Column('address_line1', sa.String(), nullable=True),
        sa.Column('address_line2', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('state', sa.String(length=2), nullable=True),
        sa.Column('zip_code', sa.String(length=10), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('ein', sa.String(), nullable=True),
        sa.Column('bank_routing_number', sa.String(length=9), nullable=True),
        sa.Column('bank_account_number_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('bank_account_last_four', sa.String(length=4), nullable=True),
        sa.Column('payment_method', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_third_party_entities_name', 'third_party_entities', ['name'])
    op.create_index('ix_third_party_entities_entity_type', 'third_party_entities', ['entity_type'])

    op.add_column(
        'deduction_orders',
        sa.Column(
            'third_party_entity_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('third_party_entities.id'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('deduction_orders', 'third_party_entity_id')
    op.drop_index('ix_third_party_entities_entity_type', table_name='third_party_entities')
    op.drop_index('ix_third_party_entities_name', table_name='third_party_entities')
    op.drop_table('third_party_entities')
