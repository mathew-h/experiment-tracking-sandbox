"""fix ionic conductivity units

Revision ID: 632efc85843e
Revises: 1e2ca98f0dfe
Create Date: 2026-02-04 09:28:17.840582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '632efc85843e'
down_revision: Union[str, None] = '1e2ca98f0dfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()

    # 0. CRITICAL: Clean up temp tables from failed migrations
    temp_table = '_alembic_tmp_elemental_analysis'
    if temp_table in all_tables:
        op.drop_table(temp_table)

    # 1. Update elemental_analysis: make external_analysis_id NOT NULL
    # Using batch mode for ALTER COLUMN logic (changing nullability)
    # CRITICAL: We must handle existing NULLs before altering column to NOT NULL
    op.execute("DELETE FROM elemental_analysis WHERE external_analysis_id IS NULL")
    
    with op.batch_alter_table('elemental_analysis', schema=None) as batch_op:
        batch_op.alter_column('external_analysis_id',
               existing_type=sa.INTEGER(),
               nullable=False)

    # 2. Update experiments: remove/add FK for parent_experiment_fk
    # Skip self-referential FK constraint in SQLite to avoid circular dependency
    # We will SKIP adding this constraint in SQLite.
    
    # 3. Add missing initial_conductivity_mS_cm column to experimental_conditions
    # Check if column exists to be idempotent
    exp_conditions_columns = [col['name'] for col in inspector.get_columns('experimental_conditions')]
    if 'initial_conductivity_mS_cm' not in exp_conditions_columns:
        with op.batch_alter_table('experimental_conditions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('initial_conductivity_mS_cm', sa.Float(), nullable=True))

    # 4. Update external_analyses: drop FK to pxrf_readings
    # Define naming convention to handle unnamed FKs in SQLite
    # This allows us to refer to the unnamed constraint by a deterministic name during batch op
    naming_convention = {
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    }
    
    # Check if FK exists (regardless of name) to be idempotent
    fks = inspector.get_foreign_keys('external_analyses')
    has_pxrf_fk = any(fk['referred_table'] == 'pxrf_readings' for fk in fks)
    
    if has_pxrf_fk:
        with op.batch_alter_table('external_analyses', schema=None, naming_convention=naming_convention) as batch_op:
            batch_op.drop_constraint(
                "fk_external_analyses_pxrf_reading_no_pxrf_readings",
                type_='foreignkey'
            )


def downgrade() -> None:
    """Downgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    
    # 1. Remove initial_conductivity_mS_cm column from experimental_conditions
    exp_conditions_columns = [col['name'] for col in inspector.get_columns('experimental_conditions')]
    if 'initial_conductivity_mS_cm' in exp_conditions_columns:
        with op.batch_alter_table('experimental_conditions', schema=None) as batch_op:
            batch_op.drop_column('initial_conductivity_mS_cm')

    # 2. Re-add FK to external_analyses
    with op.batch_alter_table('external_analyses', schema=None) as batch_op:
        # Re-add FK to pxrf_readings if it doesn't exist
        fks = inspector.get_foreign_keys('external_analyses')
        has_fk = any(fk['referred_table'] == 'pxrf_readings' for fk in fks)
        if not has_fk:
            batch_op.create_foreign_key('fk_external_analyses_pxrf_reading_no_pxrf_readings', 'pxrf_readings', ['pxrf_reading_no'], ['reading_no'], ondelete='SET NULL')

    # 3. Drop parent_experiment_fk FK in experiments (if it existed)
    # Since we skipped creating it in upgrade, we technically don't need to drop it here for SQLite correctness.
    
    # 4. Revert elemental_analysis nullability
    with op.batch_alter_table('elemental_analysis', schema=None) as batch_op:
        batch_op.alter_column('external_analysis_id',
               existing_type=sa.INTEGER(),
               nullable=True)
