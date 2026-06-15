"""add member_name_history table

Revision ID: 339e336bb721
Revises: 545e1a2c9fa8
Create Date: 2026-06-15 17:34:12.106822

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '339e336bb721'
down_revision: Union[str, None] = '545e1a2c9fa8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('member_name_history',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    sa.Column('member_id', sa.UUID(), nullable=False),
    sa.Column('first_name', sa.Text(), nullable=False),
    sa.Column('middle_name', sa.Text(), nullable=True),
    sa.Column('last_name', sa.Text(), nullable=False),
    sa.Column('suffix', sa.Text(), nullable=True),
    sa.Column('effective_date', sa.Date(), nullable=False),
    sa.Column('reason', sa.String(), nullable=True),
    sa.Column('changed_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('member_name_history')
