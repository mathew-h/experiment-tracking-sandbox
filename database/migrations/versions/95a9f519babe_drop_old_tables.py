"""drop_old_tables

Revision ID: 95a9f519babe
Revises: 3d3c86ab5c20
Create Date: 2025-05-06 11:24:06.379056

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95a9f519babe'
down_revision: Union[str, None] = '3d3c86ab5c20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
