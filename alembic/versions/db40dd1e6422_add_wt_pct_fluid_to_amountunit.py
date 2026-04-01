"""add_wt_pct_fluid_to_amountunit

Revision ID: db40dd1e6422
Revises: 458f344f73d8
Create Date: 2026-04-01 15:16:00.333459

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db40dd1e6422'
down_revision: Union[str, None] = '458f344f73d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing AmountUnit values to the PostgreSQL native enum type.
    # PERCENT and WEIGHT_PERCENT were in the Python enum but never migrated.
    # WT_PCT_FLUID is new (issue #25).
    # IF NOT EXISTS is safe on databases already bootstrapped from Base.metadata.create_all.
    # On SQLite, Enum columns are VARCHAR — these statements are no-ops.
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute("ALTER TYPE amountunit ADD VALUE IF NOT EXISTS 'PERCENT'")
        op.execute("ALTER TYPE amountunit ADD VALUE IF NOT EXISTS 'WEIGHT_PERCENT'")
        op.execute("ALTER TYPE amountunit ADD VALUE IF NOT EXISTS 'WT_PCT_FLUID'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    # Downgrade is a no-op. Remove any rows using WT_PCT_FLUID before rolling back.
    pass
