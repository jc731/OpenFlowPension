"""add payroll validation columns

Revision ID: 55fb0ada6579
Revises: b2c3d4e5f6a7
Create Date: 2026-05-06 18:44:39.597932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '55fb0ada6579'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payroll_report_rows', sa.Column('validation_warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('payroll_reports', sa.Column('warning_count', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('payroll_reports', 'warning_count')
    op.drop_column('payroll_report_rows', 'validation_warnings')
