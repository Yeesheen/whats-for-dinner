"""make_spoonacular_id_nullable_add_source_website

Revision ID: b33097420fa6
Revises: 22cb908cb225
Create Date: 2025-12-09 11:09:39.764235

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b33097420fa6'
down_revision: Union[str, None] = '22cb908cb225'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add source_website column
    op.add_column('recipes', sa.Column('source_website', sa.String(255), nullable=True))

    # For SQLite, we need to use batch operations to alter the spoonacular_id column
    with op.batch_alter_table('recipes') as batch_op:
        batch_op.alter_column('spoonacular_id',
                              existing_type=sa.Integer(),
                              nullable=True)


def downgrade() -> None:
    # Remove source_website column
    op.drop_column('recipes', 'source_website')

    # Revert spoonacular_id to non-nullable
    with op.batch_alter_table('recipes') as batch_op:
        batch_op.alter_column('spoonacular_id',
                              existing_type=sa.Integer(),
                              nullable=False)
