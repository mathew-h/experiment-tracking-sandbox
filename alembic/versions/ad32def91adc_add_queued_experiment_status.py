"""add_queued_experiment_status

Revision ID: ad32def91adc
Revises: 9c358174ea54
Create Date: 2026-04-06

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ad32def91adc'
down_revision: Union[str, None] = '9c358174ea54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add QUEUED to the experimentstatus PostgreSQL native enum type (issue #33).
    # IF NOT EXISTS is safe on databases already bootstrapped from Base.metadata.create_all.
    # On SQLite, Enum columns are VARCHAR — this statement is a no-op.
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute("ALTER TYPE experimentstatus ADD VALUE IF NOT EXISTS 'QUEUED'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    # Downgrade is a no-op. Remove any rows using QUEUED before rolling back.
    pass
