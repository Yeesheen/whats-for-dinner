"""add_max_ingredients_per_week_to_user

Revision ID: 53e887b48cd7
Revises: b33097420fa6
Create Date: 2025-12-10 10:44:24.039021

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53e887b48cd7'
down_revision: Union[str, None] = 'b33097420fa6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add max_ingredients_per_week column with default value of 20
    op.add_column('users', sa.Column('max_ingredients_per_week', sa.Integer(), server_default='20', nullable=True))


def downgrade() -> None:
    # Remove max_ingredients_per_week column
    op.drop_column('users', 'max_ingredients_per_week')
