"""titration changes

Revision ID: e133154e2e58
Revises: 80cf54c5d3a6
Create Date: 2025-10-20 14:35:06.002743

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = 'e133154e2e58'
down_revision: Union[str, None] = '80cf54c5d3a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create analytes table (id PK implicitly indexed; do not add index=True here to avoid duplicate index names)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if 'analytes' not in existing_tables:
        op.create_table(
            'analytes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('analyte_symbol', sa.String(), nullable=False),
            sa.Column('unit', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        # Unique index on analyte_symbol (create only if it does not already exist)
        op.create_index(op.f('ix_analytes_analyte_symbol'), 'analytes', ['analyte_symbol'], unique=True)
    else:
        # Table already exists (likely due to a prior partial run); ensure unique index exists
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('analytes')}
        if 'ix_analytes_analyte_symbol' not in existing_indexes:
            try:
                op.create_index(op.f('ix_analytes_analyte_symbol'), 'analytes', ['analyte_symbol'], unique=True)
            except Exception:
                pass

    # Drop leftover temp table from prior failed runs (SQLite batch uses this name)
    try:
        bind.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_elemental_analysis"))
    except Exception:
        pass

    # Drop old unique index on external_analysis_id BEFORE batch (prevents SQLite batch from recreating it)
    try:
        op.drop_index('ix_elemental_analysis_external_analysis_id', table_name='elemental_analysis')
    except Exception:
        pass

    # Skip batch if schema already reflects the new shape (idempotent re-run safety)
    cols = {c['name'] for c in inspector.get_columns('elemental_analysis')}
    needs_batch = not (
        'sample_id' in cols and 'analyte_id' in cols and 'analyte_composition' in cols and 'external_analysis_id' not in cols
    )

    if needs_batch:
        # SQLite-compatible table changes for elemental_analysis
        with op.batch_alter_table('elemental_analysis', schema=None) as batch_op:
            # Add new columns (nullable for safer migrations on SQLite)
            batch_op.add_column(sa.Column('sample_id', sa.String(), nullable=True))
            batch_op.add_column(sa.Column('analyte_id', sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column('analyte_composition', sa.Float(), nullable=True))

            # Drop obsolete columns (batch mode recreates table on SQLite)
            batch_op.drop_column('external_analysis_id')
            batch_op.drop_column('detection_method')
            batch_op.drop_column('detection_limits')
            batch_op.drop_column('analytical_conditions')
            batch_op.drop_column('major_elements')
            batch_op.drop_column('minor_elements')
            batch_op.drop_column('trace_elements')

            # Create constraints and indexes within batch (required for SQLite)
            batch_op.create_unique_constraint('uq_elemental_analysis_sample_analyte', ['sample_id', 'analyte_id'])
            batch_op.create_foreign_key('fk_elemental_analysis_sample_id', 'sample_info', ['sample_id'], ['sample_id'], ondelete='CASCADE')
            batch_op.create_foreign_key('fk_elemental_analysis_analyte_id', 'analytes', ['analyte_id'], ['id'], ondelete='CASCADE')
            batch_op.create_index(op.f('ix_elemental_analysis_analyte_id'), ['analyte_id'], unique=False)
            batch_op.create_index(op.f('ix_elemental_analysis_sample_id'), ['sample_id'], unique=False)


    # Post-batch: nothing further needed for constraints on SQLite

    # Note: We intentionally skip altering experiments.status to Enum for SQLite portability


def downgrade() -> None:
    """Downgrade schema."""
    # Remove new constraints and indexes
    try:
        op.drop_constraint('uq_elemental_analysis_sample_analyte', 'elemental_analysis', type_='unique')
    except Exception:
        pass
    try:
        op.drop_constraint('fk_elemental_analysis_sample_id', 'elemental_analysis', type_='foreignkey')
    except Exception:
        pass
    try:
        op.drop_constraint('fk_elemental_analysis_analyte_id', 'elemental_analysis', type_='foreignkey')
    except Exception:
        pass
    try:
        op.drop_index(op.f('ix_elemental_analysis_sample_id'), table_name='elemental_analysis')
    except Exception:
        pass
    try:
        op.drop_index(op.f('ix_elemental_analysis_analyte_id'), table_name='elemental_analysis')
    except Exception:
        pass

    # SQLite-compatible revert of elemental_analysis table structure
    with op.batch_alter_table('elemental_analysis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('external_analysis_id', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('detection_method', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('detection_limits', sqlite.JSON(), nullable=True))
        batch_op.add_column(sa.Column('analytical_conditions', sqlite.JSON(), nullable=True))
        batch_op.add_column(sa.Column('major_elements', sqlite.JSON(), nullable=True))
        batch_op.add_column(sa.Column('minor_elements', sqlite.JSON(), nullable=True))
        batch_op.add_column(sa.Column('trace_elements', sqlite.JSON(), nullable=True))

        # Drop newly added columns
        batch_op.drop_column('analyte_composition')
        batch_op.drop_column('analyte_id')
        batch_op.drop_column('sample_id')

    # Recreate old index and FK to external_analyses
    try:
        op.create_index('ix_elemental_analysis_external_analysis_id', 'elemental_analysis', ['external_analysis_id'], unique=True)
    except Exception:
        pass
    try:
        op.create_foreign_key('fk_elemental_analysis_external_analysis_id', 'elemental_analysis', 'external_analyses', ['external_analysis_id'], ['id'], ondelete='CASCADE')
    except Exception:
        pass

    # Drop analytes table
    try:
        op.drop_index(op.f('ix_analytes_id'), table_name='analytes')
        op.drop_index(op.f('ix_analytes_analyte_symbol'), table_name='analytes')
    except Exception:
        pass
    try:
        op.drop_table('analytes')
    except Exception:
        pass
