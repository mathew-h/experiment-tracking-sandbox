"""update_experiment_statuses

Revision ID: 39fa8cb5c06a
Revises: 95a9f519babe
Create Date: 2025-06-05 11:12:42.420091

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39fa8cb5c06a'
down_revision: Union[str, None] = '95a9f519babe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define current and new enum values for clarity and potential downgrade logic
# These were the values likely present in the DB enum before this migration
# (assuming 'ONGOING' is the only new one being added by this specific models.py change)
EXISTING_DB_ENUM_VALUES = ('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED')
# The new value being introduced by the corresponding models.py change
NEW_ENUM_VALUE_TO_ADD = 'ONGOING'
# All values that should be in the DB enum after this upgrade, to support data migration
# This assumes your database ENUM before this script already had PLANNED, IN_PROGRESS, etc.
# If not, they would also need "ADD VALUE IF NOT EXISTS"
FINAL_ENUM_VALUES_FOR_TRANSITION = ('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED', NEW_ENUM_VALUE_TO_ADD)


def upgrade() -> None:
    """
    Upgrade schema.
    For SQLite, if the 'status' column is VARCHAR and there are no specific
    database-level CHECK constraints being modified for this Enum change,
    this migration might be a no-op at the SQL level.
    The primary changes are in models.py and handled by the data migration script.
    If Alembic auto-generated this as 'pass', it indicates no direct DDL was needed for SQLite.
    """
    pass


def downgrade() -> None:
    """
    Downgrade schema.
    Similar to upgrade, if no DDL was executed, downgrade is also a no-op.
    """
    pass
