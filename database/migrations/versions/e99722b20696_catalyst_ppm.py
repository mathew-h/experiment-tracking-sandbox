"""catalyst_ppm

Revision ID: e99722b20696
Revises: c9a8db8d2142
Create Date: 2025-06-16 10:42:27.090465

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e99722b20696'
down_revision: Union[str, None] = 'c9a8db8d2142'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('experimental_conditions', sa.Column('catalyst_ppm', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('experimental_conditions', 'catalyst_ppm')
