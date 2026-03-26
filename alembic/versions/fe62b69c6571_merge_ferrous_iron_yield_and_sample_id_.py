"""merge ferrous iron yield and sample id branches

Revision ID: fe62b69c6571
Revises: c095022cadbd, d275ae3e1994
Create Date: 2026-03-24 20:48:07.950489

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe62b69c6571'
down_revision: Union[str, None] = ('c095022cadbd', 'd275ae3e1994')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
