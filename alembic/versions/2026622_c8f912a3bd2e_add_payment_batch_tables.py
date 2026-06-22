"""add payment batch and payment events tables

Revision ID: c8f912a3bd2e
Revises: 339e336bb721
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8f912a3bd2e'
down_revision: Union[str, None] = '339e336bb721'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payment_batches',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('batch_date', sa.Date(), nullable=False),
        sa.Column('payment_type', sa.String(), nullable=False, server_default='annuity'),
        sa.Column('status', sa.String(), nullable=False, server_default='draft'),
        sa.Column('total_gross', sa.Numeric(14, 2), nullable=True),
        sa.Column('total_net', sa.Numeric(14, 2), nullable=True),
        sa.Column('payment_count', sa.Integer(), nullable=True),
        sa.Column('dispatch_format', sa.String(), nullable=True),
        sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reconciled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.add_column(
        'benefit_payments',
        sa.Column('batch_id', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_benefit_payments_batch_id',
        'benefit_payments', 'payment_batches',
        ['batch_id'], ['id'],
    )

    op.create_table(
        'payment_events',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('batch_id', sa.UUID(), nullable=True),
        sa.Column('payment_id', sa.UUID(), nullable=True),
        sa.Column('member_id', sa.UUID(), nullable=True),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=True),
        sa.Column('gl_code', sa.String(), nullable=True),
        sa.Column('debit_credit', sa.String(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['payment_batches.id']),
        sa.ForeignKeyConstraint(['payment_id'], ['benefit_payments.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('payment_events')
    op.drop_constraint('fk_benefit_payments_batch_id', 'benefit_payments', type_='foreignkey')
    op.drop_column('benefit_payments', 'batch_id')
    op.drop_table('payment_batches')
