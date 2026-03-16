"""merging branches for mag susc

Revision ID: c9a8db8d2142
Revises: 1059508a9806, 37ddbacc2382
Create Date: 2025-06-16 10:42:07.732018

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9a8db8d2142'
down_revision: Union[str, None] = ('1059508a9806', '37ddbacc2382')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
