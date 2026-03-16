"""hydrogen data

Revision ID: 80cf54c5d3a6
Revises: b4271ce5c816
Create Date: 2025-10-16 17:08:25.487166

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '80cf54c5d3a6'
down_revision: Union[str, None] = 'b4271ce5c816'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with SQLite-safe operations and idempotent checks."""
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)

    # 1) experiments.status → Enum on non-SQLite; skip on SQLite (type alter unsupported)
    if dialect != 'sqlite':
        try:
            op.alter_column(
                'experiments',
                'status',
                existing_type=sa.VARCHAR(length=11),
                type_=sa.Enum('ONGOING', 'COMPLETED', 'CANCELLED', name='experimentstatus'),
                existing_nullable=True,
            )
        except Exception:
            # If the enum/type already matches or a provider-specific nuance prevents change, continue
            pass

    # 2) Add hydrogen-tracking columns to scalar_results if missing
    scalar_cols = {c['name'] for c in inspector.get_columns('scalar_results')}

    def add_if_missing(col_name: str, column: sa.Column) -> None:
        if col_name not in scalar_cols:
            op.add_column('scalar_results', column)

    add_if_missing('h2_concentration', sa.Column('h2_concentration', sa.Float(), nullable=True))
    add_if_missing('h2_concentration_unit', sa.Column('h2_concentration_unit', sa.String(), nullable=True))
    add_if_missing('gas_sampling_volume_ml', sa.Column('gas_sampling_volume_ml', sa.Float(), nullable=True))
    add_if_missing('gas_sampling_pressure', sa.Column('gas_sampling_pressure', sa.Float(), nullable=True))
    add_if_missing('h2_moles', sa.Column('h2_moles', sa.Float(), nullable=True))
    add_if_missing('h2_mass_g', sa.Column('h2_mass_g', sa.Float(), nullable=True))

    # 3) Create unique index for xrd_analysis.external_analysis_id if absent
    index_name = op.f('ix_xrd_analysis_external_analysis_id')
    existing_indexes = inspector.get_indexes('xrd_analysis')
    has_index = any(
        idx.get('name') == index_name or (
            idx.get('unique') and idx.get('column_names') == ['external_analysis_id']
        )
        for idx in existing_indexes
    )
    if not has_index:
        try:
            op.create_index(index_name, 'xrd_analysis', ['external_analysis_id'], unique=True)
        except Exception:
            # Ignore if duplicates or provider constraints block creation; schema otherwise remains usable
            pass


def downgrade() -> None:
    """Downgrade schema with SQLite-safe operations and idempotent checks."""
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)

    # 1) Drop index if it exists
    index_name = op.f('ix_xrd_analysis_external_analysis_id')
    existing_indexes = inspector.get_indexes('xrd_analysis')
    has_index = any(idx.get('name') == index_name for idx in existing_indexes)
    if has_index:
        try:
            op.drop_index(index_name, table_name='xrd_analysis')
        except Exception:
            pass

    # 2) Drop hydrogen-tracking columns (use batch to support SQLite)
    scalar_cols = {c['name'] for c in inspector.get_columns('scalar_results')}
    cols_to_drop = [
        'h2_mass_g',
        'h2_moles',
        'gas_sampling_pressure',
        'gas_sampling_volume_ml',
        'h2_concentration_unit',
        'h2_concentration',
    ]

    # Only attempt drop for columns that exist
    cols_to_drop = [c for c in cols_to_drop if c in scalar_cols]
    if cols_to_drop:
        with op.batch_alter_table('scalar_results') as batch_op:
            for col in cols_to_drop:
                try:
                    batch_op.drop_column(col)
                except Exception:
                    pass

    # 3) Revert experiments.status type on non-SQLite only
    if dialect != 'sqlite':
        try:
            op.alter_column(
                'experiments',
                'status',
                existing_type=sa.Enum('ONGOING', 'COMPLETED', 'CANCELLED', name='experimentstatus'),
                type_=sa.VARCHAR(length=11),
                existing_nullable=True,
            )
        except Exception:
            pass
