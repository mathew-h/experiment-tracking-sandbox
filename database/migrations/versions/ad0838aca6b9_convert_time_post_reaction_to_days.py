"""convert_time_post_reaction_to_days

Revision ID: ad0838aca6b9
Revises: 1c060cd1a0e1
Create Date: 2025-06-24 11:19:34.516788

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad0838aca6b9'
down_revision: Union[str, None] = '99fc20a201fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert time_post_reaction from hours to days and round."""
    op.execute("UPDATE experimental_results SET time_post_reaction = (time_post_reaction / 24.0)")


def downgrade() -> None:
    """Convert time_post_reaction from days back to hours."""
    # This is a lossy conversion as rounding in upgrade is irreversible.
    op.execute("UPDATE experimental_results SET time_post_reaction = time_post_reaction * 24.0")
