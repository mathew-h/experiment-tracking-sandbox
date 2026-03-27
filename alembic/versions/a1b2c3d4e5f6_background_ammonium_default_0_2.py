"""Set default 0.2 and backfill NULL background_ammonium_concentration_mM

Revision ID: a1b2c3d4e5f6
Revises: 88c99be25944
Create Date: 2026-03-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '88c99be25944'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Set server-level default so new rows without an explicit value receive 0.2.
    op.alter_column(
        'scalar_results',
        'background_ammonium_concentration_mM',
        server_default='0.2',
        existing_type=sa.Float(),
        existing_nullable=True,
    )
    # Backfill all existing rows where the value was never recorded.
    # Column name requires double-quotes in PostgreSQL (mixed-case identifier).
    op.execute(
        'UPDATE scalar_results '
        'SET "background_ammonium_concentration_mM" = 0.2 '
        'WHERE "background_ammonium_concentration_mM" IS NULL'
    )


def downgrade() -> None:
    op.alter_column(
        'scalar_results',
        'background_ammonium_concentration_mM',
        server_default=None,
        existing_type=sa.Float(),
        existing_nullable=True,
    )
