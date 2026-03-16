"""Add Zn and update schema

Revision ID: 2b9158f20660
Revises: 34cd6e250e16
Create Date: 2025-12-04 14:07:29.594821

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = '2b9158f20660'
down_revision: Union[str, None] = '34cd6e250e16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent."""
    conn = op.get_bind()
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()

    # 1. Clean up temp tables from failed migrations
    for table_name in all_tables:
        if table_name.startswith('_alembic_tmp_'):
            op.drop_table(table_name)

    # 2. Drop dependent views BEFORE modifying tables they depend on
    op.execute("DROP VIEW IF EXISTS v_experiment_additives_summary")

    # 3. experimental_conditions modifications
    # reactor_number (add)
    # particle_size (change type Float -> String)
    
    exp_cond_columns = [col['name'] for col in inspector.get_columns('experimental_conditions')]
    
    with op.batch_alter_table('experimental_conditions', schema=None) as batch_op:
        if 'reactor_number' not in exp_cond_columns:
            batch_op.add_column(sa.Column('reactor_number', sa.Integer(), nullable=True))
        
        if 'particle_size' in exp_cond_columns:
             batch_op.alter_column('particle_size',
               existing_type=sa.Float(),
               type_=sa.String(),
               existing_nullable=True)

    # 4. pxrf_readings modifications
    # Add Zn column
    pxrf_columns = [col['name'] for col in inspector.get_columns('pxrf_readings')]
    
    if 'Zn' not in pxrf_columns:
        with op.batch_alter_table('pxrf_readings', schema=None) as batch_op:
            batch_op.add_column(sa.Column('Zn', sa.Float(), nullable=True))

    # 5. experimental_results modifications
    # time_post_reaction -> nullable=True
    with op.batch_alter_table('experimental_results', schema=None) as batch_op:
        batch_op.alter_column('time_post_reaction',
               existing_type=sa.Float(),
               nullable=True)

    # 6. elemental_analysis modifications
    # sample_id -> nullable=False
    # analyte_id -> nullable=False
    with op.batch_alter_table('elemental_analysis', schema=None) as batch_op:
        batch_op.alter_column('sample_id',
               existing_type=sa.String(),
               nullable=False)
        batch_op.alter_column('analyte_id',
               existing_type=sa.Integer(),
               nullable=False)

    # 7. Recreate view
    op.execute("""
        CREATE VIEW IF NOT EXISTS v_experiment_additives_summary AS
        SELECT e.experiment_id AS experiment_id,
               GROUP_CONCAT(c.name || ' ' || CAST(a.amount AS TEXT) || ' ' || a.unit, '; ') AS additives_summary
        FROM chemical_additives a
        JOIN experimental_conditions ec ON ec.id = a.experiment_id
        JOIN experiments e ON e.id = ec.experiment_fk
        JOIN compounds c ON c.id = a.compound_id
        GROUP BY e.experiment_id;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = inspect(conn)

    # 1. Drop view
    op.execute("DROP VIEW IF EXISTS v_experiment_additives_summary")
    
    # Reverse changes
    
    # 2. elemental_analysis -> nullable=True
    with op.batch_alter_table('elemental_analysis', schema=None) as batch_op:
        batch_op.alter_column('sample_id',
               existing_type=sa.String(),
               nullable=True)
        batch_op.alter_column('analyte_id',
               existing_type=sa.Integer(),
               nullable=True)

    # 3. experimental_results -> nullable=False
    with op.batch_alter_table('experimental_results', schema=None) as batch_op:
        batch_op.alter_column('time_post_reaction',
               existing_type=sa.Float(),
               nullable=False)

    # 4. pxrf_readings -> drop Zn
    pxrf_columns = [col['name'] for col in inspector.get_columns('pxrf_readings')]
    if 'Zn' in pxrf_columns:
        with op.batch_alter_table('pxrf_readings', schema=None) as batch_op:
            batch_op.drop_column('Zn')

    # 5. experimental_conditions
    exp_cond_columns = [col['name'] for col in inspector.get_columns('experimental_conditions')]
    
    with op.batch_alter_table('experimental_conditions', schema=None) as batch_op:
        if 'reactor_number' in exp_cond_columns:
            batch_op.drop_column('reactor_number')
        
        if 'particle_size' in exp_cond_columns:
             batch_op.alter_column('particle_size',
               existing_type=sa.String(),
               type_=sa.Float(),
               existing_nullable=True)

    # 6. Recreate view
    op.execute("""
        CREATE VIEW IF NOT EXISTS v_experiment_additives_summary AS
        SELECT e.experiment_id AS experiment_id,
               GROUP_CONCAT(c.name || ' ' || CAST(a.amount AS TEXT) || ' ' || a.unit, '; ') AS additives_summary
        FROM chemical_additives a
        JOIN experimental_conditions ec ON ec.id = a.experiment_id
        JOIN experiments e ON e.id = ec.experiment_fk
        JOIN compounds c ON c.id = a.compound_id
        GROUP BY e.experiment_id;
    """)
