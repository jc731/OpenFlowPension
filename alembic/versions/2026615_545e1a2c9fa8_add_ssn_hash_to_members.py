"""add ssn_hash to members

Revision ID: 545e1a2c9fa8
Revises: a9eee58a15f8
Create Date: 2026-06-15 17:31:21.337613

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '545e1a2c9fa8'
down_revision: Union[str, None] = 'a9eee58a15f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('members', sa.Column('ssn_hash', sa.String(length=64), nullable=True))
    op.create_unique_constraint('uq_members_ssn_hash', 'members', ['ssn_hash'])


def downgrade() -> None:
    op.drop_constraint('uq_members_ssn_hash', 'members', type_='unique')
    op.drop_column('members', 'ssn_hash')
