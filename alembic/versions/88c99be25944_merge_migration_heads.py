"""merge migration heads

Revision ID: 88c99be25944
Revises: c095022cadbd, d275ae3e1994
Create Date: 2026-03-25 16:37:21.796969

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88c99be25944'
down_revision: Union[str, None] = ('c095022cadbd', 'd275ae3e1994')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
