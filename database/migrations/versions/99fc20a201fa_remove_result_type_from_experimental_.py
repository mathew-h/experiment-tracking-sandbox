"""remove_result_type_from_experimental_results

Revision ID: 99fc20a201fa
Revises: 87f4f47b5a11
Create Date: 2025-06-24 10:55:32.352130

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99fc20a201fa'
down_revision: Union[str, None] = '87f4f47b5a11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove result_type from experimental_results table."""
    with op.batch_alter_table('experimental_results', schema=None) as batch_op:
        batch_op.drop_column('result_type')


def downgrade() -> None:
    """Add result_type back to experimental_results table."""
    # Note: If you need to restore data, this downgrade is not sufficient.
    # It just restores the schema.
    with op.batch_alter_table('experimental_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column('result_type', sa.VARCHAR(length=4), nullable=False, server_default='NMR'))
