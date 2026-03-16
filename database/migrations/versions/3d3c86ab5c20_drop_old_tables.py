"""drop_old_tables

Revision ID: 3d3c86ab5c20
Revises: ff0fba032e06
Create Date: 2025-05-06 11:23:10.231302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d3c86ab5c20'
down_revision: Union[str, None] = 'ff0fba032e06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('experimental_data')
    op.drop_table('results')  
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
