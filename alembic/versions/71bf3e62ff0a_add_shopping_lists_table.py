"""add_shopping_lists_table

Revision ID: 71bf3e62ff0a
Revises: 53e887b48cd7
Create Date: 2025-12-12 10:46:37.425253

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '71bf3e62ff0a'
down_revision: Union[str, None] = '53e887b48cd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shopping_lists',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('share_token', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('ingredients', sa.Text(), nullable=False),
        sa.Column('recipe_ids', sa.Text(), nullable=True),
        sa.Column('recipe_titles', sa.Text(), nullable=True),
        sa.Column('total_ingredients', sa.Integer(), nullable=True),
        sa.Column('ingredient_budget', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('share_token')
    )
    op.create_index(op.f('ix_shopping_lists_share_token'), 'shopping_lists', ['share_token'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_shopping_lists_share_token'), table_name='shopping_lists')
    op.drop_table('shopping_lists')
