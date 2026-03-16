"""add_mag_susc

Revision ID: 37ddbacc2382
Revises: 39fa8cb5c06a
Create Date: 2025-06-12 16:17:56.503127

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37ddbacc2382'
down_revision: Union[str, None] = '39fa8cb5c06a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
