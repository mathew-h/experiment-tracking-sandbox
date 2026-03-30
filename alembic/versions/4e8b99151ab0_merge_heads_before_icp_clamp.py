"""merge heads before icp clamp

Revision ID: 4e8b99151ab0
Revises: a1b2c3d4e5f6, fe62b69c6571
Create Date: 2026-03-30 15:34:35.063762

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e8b99151ab0'
down_revision: Union[str, None] = ('a1b2c3d4e5f6', 'fe62b69c6571')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
