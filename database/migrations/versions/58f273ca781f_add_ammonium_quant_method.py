"""add ammonium quant method

Revision ID: 58f273ca781f
Revises: 226e3f8d5c78
Create Date: 2026-01-27 16:08:58.505776

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '58f273ca781f'
down_revision: Union[str, None] = '226e3f8d5c78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("scalar_results")]

    if "ammonium_quant_method" not in columns:
        op.add_column("scalar_results", sa.Column("ammonium_quant_method", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("scalar_results")]

    if "ammonium_quant_method" in columns:
        op.drop_column("scalar_results", "ammonium_quant_method")
