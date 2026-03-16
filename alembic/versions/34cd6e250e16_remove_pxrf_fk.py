"""remove pxrf fk

Revision ID: 34cd6e250e16
Revises: a1b294160d37
Create Date: 2025-11-05 10:15:31.556071

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '34cd6e250e16'
down_revision: Union[str, None] = 'a1b294160d37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove FK constraint from external_analyses.pxrf_reading_no - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    
    # Get foreign keys for external_analyses table
    fks = inspector.get_foreign_keys('external_analyses')
    
    # Find the FK constraint for pxrf_reading_no
    pxrf_fk_name = None
    for fk in fks:
        if 'pxrf_reading_no' in fk.get('constrained_columns', []):
            pxrf_fk_name = fk.get('name')
            break
    
    # Only drop if FK exists
    if pxrf_fk_name:
        # Use batch mode for constraint operations in SQLite
        with op.batch_alter_table('external_analyses', schema=None) as batch_op:
            batch_op.drop_constraint(pxrf_fk_name, type_='foreignkey')


def downgrade() -> None:
    """Re-add FK constraint to external_analyses.pxrf_reading_no - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    
    # Get foreign keys for external_analyses table
    fks = inspector.get_foreign_keys('external_analyses')
    
    # Check if FK already exists
    pxrf_fk_exists = any('pxrf_reading_no' in fk.get('constrained_columns', []) for fk in fks)
    
    # Only create if FK doesn't exist
    if not pxrf_fk_exists:
        # Use batch mode for constraint operations in SQLite
        with op.batch_alter_table('external_analyses', schema=None) as batch_op:
            batch_op.create_foreign_key(
                'fk_external_analyses_pxrf_reading_no',
                'pxrf_readings',
                ['pxrf_reading_no'],
                ['reading_no'],
                ondelete='SET NULL'
            )
