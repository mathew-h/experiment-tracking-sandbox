"""xrd

Revision ID: b4271ce5c816
Revises: 207e399920a6
Create Date: 2025-10-15 10:41:48.444749

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4271ce5c816'
down_revision: Union[str, None] = '207e399920a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Use inspector to make the migration idempotent for partially applied upgrades
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Create xrd_phases table if it does not exist
    existing_tables = set(inspector.get_table_names())
    if 'xrd_phases' not in existing_tables:
        op.create_table(
            'xrd_phases',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('sample_id', sa.String(), nullable=False),
            sa.Column('external_analysis_id', sa.Integer(), nullable=True),
            sa.Column('mineral_name', sa.String(), nullable=False),
            sa.Column('amount', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['external_analysis_id'], ['external_analyses.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['sample_id'], ['sample_info.sample_id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('sample_id', 'mineral_name', name='uq_xrd_phase_sample_mineral')
        )
        op.create_index(op.f('ix_xrd_phases_external_analysis_id'), 'xrd_phases', ['external_analysis_id'], unique=False)
        op.create_index(op.f('ix_xrd_phases_id'), 'xrd_phases', ['id'], unique=False)
        op.create_index(op.f('ix_xrd_phases_mineral_name'), 'xrd_phases', ['mineral_name'], unique=False)
        op.create_index(op.f('ix_xrd_phases_sample_id'), 'xrd_phases', ['sample_id'], unique=False)

    # Add columns to chemical_additives only if missing
    chem_cols = {c['name'] for c in inspector.get_columns('chemical_additives')}
    if 'elemental_metal_mass' not in chem_cols:
        op.add_column('chemical_additives', sa.Column('elemental_metal_mass', sa.Float(), nullable=True))
    if 'catalyst_percentage' not in chem_cols:
        op.add_column('chemical_additives', sa.Column('catalyst_percentage', sa.Float(), nullable=True))
    if 'catalyst_ppm' not in chem_cols:
        op.add_column('chemical_additives', sa.Column('catalyst_ppm', sa.Float(), nullable=True))

    # Add columns to compounds only if missing
    comp_cols = {c['name'] for c in inspector.get_columns('compounds')}
    if 'preferred_unit' not in comp_cols:
        op.add_column('compounds', sa.Column('preferred_unit', sa.Enum('GRAM', 'MILLIGRAM', 'MICROGRAM', 'KILOGRAM', 'MICROLITER', 'MILLILITER', 'LITER', 'MICROMOLE', 'MILLIMOLE', 'MOLE', 'PPM', 'MILLIMOLAR', 'MOLAR', name='amountunit'), nullable=True))
    if 'catalyst_formula' not in comp_cols:
        op.add_column('compounds', sa.Column('catalyst_formula', sa.String(length=50), nullable=True))
    if 'elemental_fraction' not in comp_cols:
        op.add_column('compounds', sa.Column('elemental_fraction', sa.Float(), nullable=True))

    # SQLite does not support ALTER COLUMN TYPE; skip for sqlite since Enum is stored as TEXT anyway
    if bind.dialect.name != 'sqlite':
        op.alter_column('experiments', 'status',
                   existing_type=sa.VARCHAR(length=11),
                   type_=sa.Enum('ONGOING', 'COMPLETED', 'CANCELLED', name='experimentstatus'),
                   existing_nullable=True)

    # Drop description column from result_files only if it exists
    res_cols = {c['name'] for c in inspector.get_columns('result_files')}
    if 'description' in res_cols:
        op.drop_column('result_files', 'description')
    # Removed redundant unique index on xrd_analysis.external_analysis_id; column is already unique
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # Make downgrade idempotent as well
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Add back description column only if missing
    res_cols = {c['name'] for c in inspector.get_columns('result_files')}
    if 'description' not in res_cols:
        op.add_column('result_files', sa.Column('description', sa.TEXT(), nullable=True))

    # Revert enum type change only on non-sqlite
    if bind.dialect.name != 'sqlite':
        op.alter_column('experiments', 'status',
                   existing_type=sa.Enum('ONGOING', 'COMPLETED', 'CANCELLED', name='experimentstatus'),
                   type_=sa.VARCHAR(length=11),
                   existing_nullable=True)

    # Drop columns on compounds if present
    comp_cols = {c['name'] for c in inspector.get_columns('compounds')}
    if 'elemental_fraction' in comp_cols:
        op.drop_column('compounds', 'elemental_fraction')
    if 'catalyst_formula' in comp_cols:
        op.drop_column('compounds', 'catalyst_formula')
    if 'preferred_unit' in comp_cols:
        op.drop_column('compounds', 'preferred_unit')

    # Drop columns on chemical_additives if present
    chem_cols = {c['name'] for c in inspector.get_columns('chemical_additives')}
    if 'catalyst_ppm' in chem_cols:
        op.drop_column('chemical_additives', 'catalyst_ppm')
    if 'catalyst_percentage' in chem_cols:
        op.drop_column('chemical_additives', 'catalyst_percentage')
    if 'elemental_metal_mass' in chem_cols:
        op.drop_column('chemical_additives', 'elemental_metal_mass')

    # Drop xrd_phases and its indexes if they exist
    existing_tables = set(inspector.get_table_names())
    if 'xrd_phases' in existing_tables:
        existing_indexes = {ix['name'] for ix in inspector.get_indexes('xrd_phases')}
        if op.f('ix_xrd_phases_sample_id') in existing_indexes:
            op.drop_index(op.f('ix_xrd_phases_sample_id'), table_name='xrd_phases')
        if op.f('ix_xrd_phases_mineral_name') in existing_indexes:
            op.drop_index(op.f('ix_xrd_phases_mineral_name'), table_name='xrd_phases')
        if op.f('ix_xrd_phases_id') in existing_indexes:
            op.drop_index(op.f('ix_xrd_phases_id'), table_name='xrd_phases')
        if op.f('ix_xrd_phases_external_analysis_id') in existing_indexes:
            op.drop_index(op.f('ix_xrd_phases_external_analysis_id'), table_name='xrd_phases')
        op.drop_table('xrd_phases')
    # ### end Alembic commands ###
