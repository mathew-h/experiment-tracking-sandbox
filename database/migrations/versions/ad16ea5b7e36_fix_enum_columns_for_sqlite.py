"""fix_enum_columns_for_sqlite

Revision ID: ad16ea5b7e36
Revises: dd013935d196
Create Date: 2025-10-24 11:26:57.088377

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad16ea5b7e36'
down_revision: Union[str, None] = 'dd013935d196'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite doesn't support ALTER COLUMN for type changes
    # The tables (chemical_additives, compounds, experiments) already have the correct schema
    # with enum types from previous migrations, so this migration is now a no-op
    # 
    # This migration was originally created to handle enum conversions, but the schema
    # has already been properly defined in earlier migrations
    pass


def downgrade() -> None:
    """Downgrade schema."""
    # No changes were made in upgrade, so downgrade is also a no-op
    pass
