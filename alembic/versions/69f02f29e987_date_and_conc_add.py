"""date_and_conc_add

Revision ID: 69f02f29e987
Revises: e99722b20696
Create Date: 2025-06-17 17:35:04.728787

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '69f02f29e987'
down_revision: Union[str, None] = 'e99722b20696'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table('experiments', schema=None) as batch_op:
        batch_op.alter_column('created_at',
                              existing_type=sa.DateTime(timezone=True),
                              nullable=False,
                              existing_server_default=sa.text('now()'))

    # Add solution_ammonium_concentration to scalar_results table
    op.add_column('scalar_results',
                  sa.Column('solution_ammonium_concentration', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove solution_ammonium_concentration from scalar_results table
    op.drop_column('scalar_results', 'solution_ammonium_concentration')

    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table('experiments', schema=None) as batch_op:
        batch_op.alter_column('created_at',
                              existing_type=sa.DateTime(timezone=True),
                              nullable=True,
                              existing_server_default=sa.text('now()'))
