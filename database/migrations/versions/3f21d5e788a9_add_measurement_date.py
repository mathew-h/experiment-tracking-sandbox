"""Add measurement_date to ScalarResults

Revision ID: 3f21d5e788a9
Revises: 2b9158f20660
Create Date: 2025-12-04 14:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = '3f21d5e788a9'
down_revision: Union[str, None] = '2b9158f20660'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('scalar_results')]
    
    if 'measurement_date' not in columns:
         with op.batch_alter_table('scalar_results', schema=None) as batch_op:
            batch_op.add_column(sa.Column('measurement_date', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('scalar_results')]
    
    if 'measurement_date' in columns:
        with op.batch_alter_table('scalar_results', schema=None) as batch_op:
            batch_op.drop_column('measurement_date')

