"""empty message

Revision ID: f081c805d28b
Revises: 3f21d5e788a9
Create Date: 2025-12-09 16:29:24.450875

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = 'f081c805d28b'
down_revision: Union[str, None] = '3f21d5e788a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()
    
    # 0. Clean up temp tables
    for table in all_tables:
        if table.startswith('_alembic_tmp_'):
            op.drop_table(table)

    # 1. ExternalAnalysis
    ea_cols = [c['name'] for c in inspector.get_columns('external_analyses')]
    ea_indexes = [i['name'] for i in inspector.get_indexes('external_analyses')]
    
    with op.batch_alter_table('external_analyses', schema=None) as batch_op:
        if 'experiment_fk' not in ea_cols:
            batch_op.add_column(sa.Column('experiment_fk', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_external_analyses_experiment_fk', 'experiments', ['experiment_fk'], ['id'], ondelete='CASCADE')
            
        if 'experiment_id' not in ea_cols:
             batch_op.add_column(sa.Column('experiment_id', sa.String(), nullable=True))
             
        # Alter sample_id to nullable
        batch_op.alter_column('sample_id', existing_type=sa.VARCHAR(), nullable=True)

    # Create indexes outside batch mode if possible, or inside? 
    # Batch mode supports create_index, but sometimes safer outside for SQLite (if not recreating table fully, but batch does).
    # Let's do it outside to be safe/standard with previous examples.
    
    if 'ix_external_analyses_experiment_fk' not in ea_indexes:
        # Check if index exists by name, or check coverage? Assuming name standard.
        op.create_index('ix_external_analyses_experiment_fk', 'external_analyses', ['experiment_fk'], unique=False)

    if 'ix_external_analyses_experiment_id' not in ea_indexes:
        op.create_index('ix_external_analyses_experiment_id', 'external_analyses', ['experiment_id'], unique=False)


    # 2. ElementalAnalysis
    elm_cols = [c['name'] for c in inspector.get_columns('elemental_analysis')]
    
    # Drop old unique constraint first?
    # In SQLite, constraints are part of table definition. Batch mode handles dropping by recreating.
    # But we need to tell it to drop the constraint.
    
    with op.batch_alter_table('elemental_analysis', schema=None) as batch_op:
        if 'external_analysis_id' not in elm_cols:
            batch_op.add_column(sa.Column('external_analysis_id', sa.Integer(), nullable=True)) # Nullable for migration compatibility
            batch_op.create_foreign_key('fk_elemental_analysis_external_analysis_id', 'external_analyses', ['external_analysis_id'], ['id'], ondelete='CASCADE')
        
        batch_op.alter_column('sample_id', existing_type=sa.VARCHAR(), nullable=True)

        # Drop old constraint if it exists
        # We try to drop by name.
        try:
            batch_op.drop_constraint('uq_elemental_analysis_sample_analyte', type_='unique')
        except (ValueError, sa.exc.NoSuchTableError):
            pass # Constraint might not exist or name mismatch

        # Create new unique constraint
        # Note: We keep the column nullable=True in DB, but enforce uniqueness on (external_analysis_id, analyte_id)
        batch_op.create_unique_constraint('uq_elemental_analysis_ext_analyte', ['external_analysis_id', 'analyte_id'])
        
    # Index for external_analysis_id
    # Check if index exists
    elm_indexes = [i['name'] for i in inspector.get_indexes('elemental_analysis')]
    if 'ix_elemental_analysis_external_analysis_id' not in elm_indexes:
        op.create_index('ix_elemental_analysis_external_analysis_id', 'elemental_analysis', ['external_analysis_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    
    # 1. ElementalAnalysis
    elm_cols = [c['name'] for c in inspector.get_columns('elemental_analysis')]
    elm_indexes = [i['name'] for i in inspector.get_indexes('elemental_analysis')]

    if 'ix_elemental_analysis_external_analysis_id' in elm_indexes:
        op.drop_index('ix_elemental_analysis_external_analysis_id', table_name='elemental_analysis')

    with op.batch_alter_table('elemental_analysis', schema=None) as batch_op:
        if 'external_analysis_id' in elm_cols:
            # Drop constraint first
            try:
                batch_op.drop_constraint('uq_elemental_analysis_ext_analyte', type_='unique')
            except ValueError:
                pass
            batch_op.drop_column('external_analysis_id')

        # Revert sample_id to non-nullable (might fail if we have nulls now)
        # batch_op.alter_column('sample_id', existing_type=sa.VARCHAR(), nullable=False) 
        # Risky to revert nullability if data changed. Let's try.
        batch_op.alter_column('sample_id', existing_type=sa.VARCHAR(), nullable=False)

        # Restore old constraint
        batch_op.create_unique_constraint('uq_elemental_analysis_sample_analyte', ['sample_id', 'analyte_id'])

    # 2. ExternalAnalysis
    ea_cols = [c['name'] for c in inspector.get_columns('external_analyses')]
    ea_indexes = [i['name'] for i in inspector.get_indexes('external_analyses')]
    
    if 'ix_external_analyses_experiment_id' in ea_indexes:
        op.drop_index('ix_external_analyses_experiment_id', table_name='external_analyses')
    if 'ix_external_analyses_experiment_fk' in ea_indexes:
        op.drop_index('ix_external_analyses_experiment_fk', table_name='external_analyses')

    with op.batch_alter_table('external_analyses', schema=None) as batch_op:
        if 'experiment_id' in ea_cols:
            batch_op.drop_column('experiment_id')
        if 'experiment_fk' in ea_cols:
            batch_op.drop_column('experiment_fk')
        
        # Revert sample_id to non-nullable
        batch_op.alter_column('sample_id', existing_type=sa.VARCHAR(), nullable=False)
