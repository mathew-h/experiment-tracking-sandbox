"""ICP date fields

Revision ID: ff30f56e6033
Revises: 6bd58ee7bf51
Create Date: 2026-02-13 08:01:16.372568

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from alembic import context
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'ff30f56e6033'
down_revision: Union[str, None] = '6bd58ee7bf51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent."""
    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()

    # Clean up leftover Alembic temp tables from failed SQLite batch migrations.
    for temp_table in ("_alembic_tmp_icp_results", "_alembic_tmp_experiments"):
        if temp_table in all_tables:
            op.drop_table(temp_table)

    # Only apply intended ICP date-field additions.
    if "icp_results" not in all_tables:
        return

    columns = [col["name"] for col in inspector.get_columns("icp_results")]
    if "measurement_date" not in columns:
        op.add_column(
            "icp_results",
            sa.Column("measurement_date", sa.DateTime(timezone=True), nullable=True),
        )
    if "sample_date" not in columns:
        op.add_column(
            "icp_results",
            sa.Column("sample_date", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema - SQLite compatible and idempotent."""
    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()

    # Clean up leftover Alembic temp tables from failed SQLite batch migrations.
    for temp_table in ("_alembic_tmp_icp_results", "_alembic_tmp_experiments"):
        if temp_table in all_tables:
            op.drop_table(temp_table)

    if "icp_results" not in all_tables:
        return

    columns = [col["name"] for col in inspector.get_columns("icp_results")]
    if "sample_date" in columns:
        op.drop_column("icp_results", "sample_date")
    if "measurement_date" in columns:
        op.drop_column("icp_results", "measurement_date")
