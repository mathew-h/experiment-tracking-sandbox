"""make_result_description_mandatory

Revision ID: 87f4f47b5a11
Revises: ebdffbdff6d0
Create Date: 2025-06-24 10:52:18.970990

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87f4f47b5a11'
down_revision: Union[str, None] = 'ebdffbdff6d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make result description non-nullable."""
    # Step 1: Update existing NULL values to an empty string to avoid constraint violations.
    op.execute("UPDATE experimental_results SET description = '' WHERE description IS NULL")

    # Step 2: Use batch mode to alter the column for SQLite compatibility.
    with op.batch_alter_table('experimental_results', schema=None) as batch_op:
        batch_op.alter_column('description',
               existing_type=sa.TEXT(),
               nullable=False)


def downgrade() -> None:
    """Revert result description to be nullable."""
    with op.batch_alter_table('experimental_results', schema=None) as batch_op:
        batch_op.alter_column('description',
               existing_type=sa.TEXT(),
               nullable=True)
