"""normalized time buckets

Revision ID: 6bd58ee7bf51
Revises: 632efc85843e
Create Date: 2026-02-10 12:03:37.526380

Adds time_post_reaction_days, time_post_reaction_bucket_days,
cumulative_time_post_reaction_days, and is_primary_timepoint_result
to experimental_results. Renames old time_post_reaction column.
Also cleans up deprecated initial_conductivity column from
experimental_conditions (replaced by initial_conductivity_mS_cm
in prior migration 632efc85843e).

Self-referential FK on experiments.parent_experiment_fk is handled
by the SQLAlchemy ORM model and is NOT added as a DB constraint
(SQLite circular dependency limitation).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6bd58ee7bf51'
down_revision: Union[str, None] = '632efc85843e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()

    # 0. Clean up leftover temp tables from any failed prior runs
    for temp_table in (
        '_alembic_tmp_experimental_results',
        '_alembic_tmp_experimental_conditions',
    ):
        if temp_table in all_tables:
            op.drop_table(temp_table)

    # 0b. Drop ALL views that reference tables we'll batch-alter.
    #     SQLite validates view dependencies during batch-mode table renames,
    #     so views must be gone before any batch_alter_table on their tables.
    #     They will be recreated at the end of this migration.
    op.execute("DROP VIEW IF EXISTS v_primary_experiment_results")
    op.execute("DROP VIEW IF EXISTS v_experiment_additives_summary")

    # ------------------------------------------------------------------
    # 1. experimental_results — add new columns
    # ------------------------------------------------------------------
    er_columns = [col['name'] for col in inspector.get_columns('experimental_results')]
    er_indexes = [idx['name'] for idx in inspector.get_indexes('experimental_results')]

    if 'time_post_reaction_days' not in er_columns:
        op.add_column('experimental_results',
                       sa.Column('time_post_reaction_days', sa.Float(), nullable=True))

    if 'time_post_reaction_bucket_days' not in er_columns:
        op.add_column('experimental_results',
                       sa.Column('time_post_reaction_bucket_days', sa.Float(), nullable=True))

    if 'cumulative_time_post_reaction_days' not in er_columns:
        op.add_column('experimental_results',
                       sa.Column('cumulative_time_post_reaction_days', sa.Float(), nullable=True))

    if 'is_primary_timepoint_result' not in er_columns:
        op.add_column('experimental_results',
                       sa.Column('is_primary_timepoint_result', sa.Boolean(),
                                 server_default=sa.text('1'), nullable=False))

    # ------------------------------------------------------------------
    # 2. experimental_results — copy data from old column, then drop it
    # ------------------------------------------------------------------
    # Refresh columns after adds
    er_columns = [col['name'] for col in inspector.get_columns('experimental_results')]

    if 'time_post_reaction' in er_columns and 'time_post_reaction_days' in er_columns:
        # Copy existing values into the new column
        op.execute(
            "UPDATE experimental_results "
            "SET time_post_reaction_days = time_post_reaction "
            "WHERE time_post_reaction IS NOT NULL"
        )

        # Drop old index BEFORE batch mode (rule: drop indexes before dropping columns)
        if 'ix_experimental_results_time_post_reaction' in er_indexes:
            op.drop_index('ix_experimental_results_time_post_reaction',
                          table_name='experimental_results')

        # Drop old time_post_reaction_bucket index if it exists
        if 'ix_experimental_results_time_post_reaction_bucket' in er_indexes:
            op.drop_index('ix_experimental_results_time_post_reaction_bucket',
                          table_name='experimental_results')

        # Drop old column via batch mode (SQLite requires batch for column drops)
        with op.batch_alter_table('experimental_results', schema=None) as batch_op:
            batch_op.drop_column('time_post_reaction')
            # Also drop time_post_reaction_bucket if it exists
            er_columns_refresh = [col['name'] for col in inspector.get_columns('experimental_results')]
            if 'time_post_reaction_bucket' in er_columns_refresh:
                batch_op.drop_column('time_post_reaction_bucket')

    # ------------------------------------------------------------------
    # 3. experimental_results — create new indexes
    # ------------------------------------------------------------------
    # Refresh indexes after batch mode
    er_indexes = [idx['name'] for idx in inspector.get_indexes('experimental_results')]

    if 'ix_experimental_results_time_post_reaction_days' not in er_indexes:
        op.create_index(op.f('ix_experimental_results_time_post_reaction_days'),
                        'experimental_results', ['time_post_reaction_days'], unique=False)

    if 'ix_experimental_results_time_post_reaction_bucket_days' not in er_indexes:
        op.create_index(op.f('ix_experimental_results_time_post_reaction_bucket_days'),
                        'experimental_results', ['time_post_reaction_bucket_days'], unique=False)

    if 'ix_experimental_results_cumulative_time_post_reaction_days' not in er_indexes:
        op.create_index(op.f('ix_experimental_results_cumulative_time_post_reaction_days'),
                        'experimental_results', ['cumulative_time_post_reaction_days'], unique=False)

    if 'ix_experimental_results_is_primary_timepoint_result' not in er_indexes:
        op.create_index(op.f('ix_experimental_results_is_primary_timepoint_result'),
                        'experimental_results', ['is_primary_timepoint_result'], unique=False)

    if 'uq_primary_result_per_experiment_bucket' not in er_indexes:
        op.create_index(
            'uq_primary_result_per_experiment_bucket',
            'experimental_results',
            ['experiment_fk', 'time_post_reaction_bucket_days'],
            unique=True,
            sqlite_where=sa.text('is_primary_timepoint_result = 1'),
        )

    # ------------------------------------------------------------------
    # 4. experimental_conditions — drop deprecated initial_conductivity
    #    (replaced by initial_conductivity_mS_cm in migration 632efc85843e)
    # ------------------------------------------------------------------
    ec_columns = [col['name'] for col in inspector.get_columns('experimental_conditions')]

    if 'initial_conductivity' in ec_columns:
        with op.batch_alter_table('experimental_conditions', schema=None) as batch_op:
            batch_op.drop_column('initial_conductivity')

    # ------------------------------------------------------------------
    # 5. Recreate views that were dropped in step 0b
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE VIEW IF NOT EXISTS v_experiment_additives_summary AS
        SELECT e.experiment_id AS experiment_id,
               GROUP_CONCAT(c.name || ' ' || CAST(a.amount AS TEXT) || ' ' || a.unit, '; ') AS additives_summary
        FROM chemical_additives a
        JOIN experimental_conditions ec ON ec.id = a.experiment_id
        JOIN experiments e ON e.id = ec.experiment_fk
        JOIN compounds c ON c.id = a.compound_id
        GROUP BY e.experiment_id;
        """
    )

    # v_primary_experiment_results will be recreated automatically by
    # event_listeners.py on next app startup. No need to duplicate the
    # full view SQL here.

    # Note: Self-referential FK on experiments.parent_experiment_fk is
    # handled by the ORM model. No DB constraint is added here to avoid
    # CircularDependencyError in SQLite.


def downgrade() -> None:
    """Downgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()

    # 0. Clean up leftover temp tables
    for temp_table in (
        '_alembic_tmp_experimental_results',
        '_alembic_tmp_experimental_conditions',
    ):
        if temp_table in all_tables:
            op.drop_table(temp_table)

    # 0b. Drop views before batch operations (SQLite view dependency issue)
    op.execute("DROP VIEW IF EXISTS v_primary_experiment_results")
    op.execute("DROP VIEW IF EXISTS v_experiment_additives_summary")

    # ------------------------------------------------------------------
    # 1. Restore old time_post_reaction column
    # ------------------------------------------------------------------
    er_columns = [col['name'] for col in inspector.get_columns('experimental_results')]
    er_indexes = [idx['name'] for idx in inspector.get_indexes('experimental_results')]

    if 'time_post_reaction' not in er_columns:
        op.add_column('experimental_results',
                       sa.Column('time_post_reaction', sa.FLOAT(), nullable=True))

    # Copy data back from renamed column
    er_columns = [col['name'] for col in inspector.get_columns('experimental_results')]
    if 'time_post_reaction' in er_columns and 'time_post_reaction_days' in er_columns:
        op.execute(
            "UPDATE experimental_results "
            "SET time_post_reaction = time_post_reaction_days "
            "WHERE time_post_reaction_days IS NOT NULL"
        )

    # ------------------------------------------------------------------
    # 2. Drop new indexes
    # ------------------------------------------------------------------
    er_indexes = [idx['name'] for idx in inspector.get_indexes('experimental_results')]

    if 'uq_primary_result_per_experiment_bucket' in er_indexes:
        op.drop_index('uq_primary_result_per_experiment_bucket',
                       table_name='experimental_results',
                       sqlite_where=sa.text('is_primary_timepoint_result = 1'))

    if 'ix_experimental_results_time_post_reaction_days' in er_indexes:
        op.drop_index(op.f('ix_experimental_results_time_post_reaction_days'),
                       table_name='experimental_results')

    if 'ix_experimental_results_time_post_reaction_bucket_days' in er_indexes:
        op.drop_index(op.f('ix_experimental_results_time_post_reaction_bucket_days'),
                       table_name='experimental_results')

    if 'ix_experimental_results_is_primary_timepoint_result' in er_indexes:
        op.drop_index(op.f('ix_experimental_results_is_primary_timepoint_result'),
                       table_name='experimental_results')

    if 'ix_experimental_results_cumulative_time_post_reaction_days' in er_indexes:
        op.drop_index(op.f('ix_experimental_results_cumulative_time_post_reaction_days'),
                       table_name='experimental_results')

    # ------------------------------------------------------------------
    # 3. Drop new columns (batch mode required for column drops in SQLite)
    # ------------------------------------------------------------------
    er_columns = [col['name'] for col in inspector.get_columns('experimental_results')]
    cols_to_drop = [
        c for c in (
            'is_primary_timepoint_result',
            'cumulative_time_post_reaction_days',
            'time_post_reaction_bucket_days',
            'time_post_reaction_days',
        )
        if c in er_columns
    ]

    if cols_to_drop:
        with op.batch_alter_table('experimental_results', schema=None) as batch_op:
            for col in cols_to_drop:
                batch_op.drop_column(col)

    # Restore old index
    er_indexes = [idx['name'] for idx in inspector.get_indexes('experimental_results')]
    if 'ix_experimental_results_time_post_reaction' not in er_indexes:
        er_columns = [col['name'] for col in inspector.get_columns('experimental_results')]
        if 'time_post_reaction' in er_columns:
            op.create_index('ix_experimental_results_time_post_reaction',
                            'experimental_results', ['time_post_reaction'], unique=False)

    # ------------------------------------------------------------------
    # 4. Restore deprecated initial_conductivity column
    # ------------------------------------------------------------------
    ec_columns = [col['name'] for col in inspector.get_columns('experimental_conditions')]

    if 'initial_conductivity' not in ec_columns:
        op.add_column('experimental_conditions',
                       sa.Column('initial_conductivity', sa.FLOAT(), nullable=True))
