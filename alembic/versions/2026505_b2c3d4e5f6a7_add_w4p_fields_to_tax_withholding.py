"""add w4p fields to tax_withholding_elections

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-05 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tax_withholding_elections',
        sa.Column('withholding_type', sa.String(), nullable=False, server_default='formula'))
    op.add_column('tax_withholding_elections',
        sa.Column('step_2_multiple_jobs', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('tax_withholding_elections',
        sa.Column('step_3_dependent_credit', sa.Numeric(12, 2), nullable=False, server_default='0'))
    op.add_column('tax_withholding_elections',
        sa.Column('step_4a_other_income', sa.Numeric(12, 2), nullable=False, server_default='0'))
    op.add_column('tax_withholding_elections',
        sa.Column('step_4b_deductions', sa.Numeric(12, 2), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('tax_withholding_elections', 'step_4b_deductions')
    op.drop_column('tax_withholding_elections', 'step_4a_other_income')
    op.drop_column('tax_withholding_elections', 'step_3_dependent_credit')
    op.drop_column('tax_withholding_elections', 'step_2_multiple_jobs')
    op.drop_column('tax_withholding_elections', 'withholding_type')
