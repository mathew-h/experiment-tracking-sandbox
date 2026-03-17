"""json_to_jsonb_and_fix_partial_index

Revision ID: a0e1f2b3c4d5
Revises: 4efd20d110e8
Create Date: 2026-03-16

- Converts all JSON columns to JSONB for PostgreSQL performance and indexability
- Fixes partial index on experimental_results: recreates with correct WHERE clause
  (sqlite_where was silently ignored by PostgreSQL, producing a full unique index)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'a0e1f2b3c4d5'
down_revision: Union[str, None] = '4efd20d110e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Fix partial index on experimental_results ---
    # The original index was created without a WHERE clause because SQLAlchemy
    # silently ignores sqlite_where on PostgreSQL. Drop and recreate correctly.
    op.drop_index(
        'uq_primary_result_per_experiment_bucket',
        table_name='experimental_results',
        if_exists=True,
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_primary_result_per_experiment_bucket
        ON experimental_results (experiment_fk, time_post_reaction_bucket_days)
        WHERE is_primary_timepoint_result = true
        """
    )

    # --- JSON → JSONB: modifications_log ---
    op.execute("ALTER TABLE modifications_log ALTER COLUMN old_values TYPE JSONB USING old_values::JSONB")
    op.execute("ALTER TABLE modifications_log ALTER COLUMN new_values TYPE JSONB USING new_values::JSONB")

    # --- JSON → JSONB: icp_results ---
    op.execute("ALTER TABLE icp_results ALTER COLUMN all_elements TYPE JSONB USING all_elements::JSONB")
    op.execute("ALTER TABLE icp_results ALTER COLUMN detection_limits TYPE JSONB USING detection_limits::JSONB")

    # --- JSON → JSONB: external_analyses ---
    op.execute("ALTER TABLE external_analyses ALTER COLUMN analysis_metadata TYPE JSONB USING analysis_metadata::JSONB")

    # --- JSON → JSONB: xrd_analysis ---
    op.execute("ALTER TABLE xrd_analysis ALTER COLUMN mineral_phases TYPE JSONB USING mineral_phases::JSONB")
    op.execute("ALTER TABLE xrd_analysis ALTER COLUMN peak_positions TYPE JSONB USING peak_positions::JSONB")
    op.execute("ALTER TABLE xrd_analysis ALTER COLUMN intensities TYPE JSONB USING intensities::JSONB")
    op.execute("ALTER TABLE xrd_analysis ALTER COLUMN d_spacings TYPE JSONB USING d_spacings::JSONB")
    op.execute("ALTER TABLE xrd_analysis ALTER COLUMN analysis_parameters TYPE JSONB USING analysis_parameters::JSONB")


def downgrade() -> None:
    # --- JSONB → JSON: xrd_analysis ---
    op.execute("ALTER TABLE xrd_analysis ALTER COLUMN analysis_parameters TYPE JSON USING analysis_parameters::TEXT::JSON")
    op.execute("ALTER TABLE xrd_analysis ALTER COLUMN d_spacings TYPE JSON USING d_spacings::TEXT::JSON")
    op.execute("ALTER TABLE xrd_analysis ALTER COLUMN intensities TYPE JSON USING intensities::TEXT::JSON")
    op.execute("ALTER TABLE xrd_analysis ALTER COLUMN peak_positions TYPE JSON USING peak_positions::TEXT::JSON")
    op.execute("ALTER TABLE xrd_analysis ALTER COLUMN mineral_phases TYPE JSON USING mineral_phases::TEXT::JSON")

    # --- JSONB → JSON: external_analyses ---
    op.execute("ALTER TABLE external_analyses ALTER COLUMN analysis_metadata TYPE JSON USING analysis_metadata::TEXT::JSON")

    # --- JSONB → JSON: icp_results ---
    op.execute("ALTER TABLE icp_results ALTER COLUMN detection_limits TYPE JSON USING detection_limits::TEXT::JSON")
    op.execute("ALTER TABLE icp_results ALTER COLUMN all_elements TYPE JSON USING all_elements::TEXT::JSON")

    # --- JSONB → JSON: modifications_log ---
    op.execute("ALTER TABLE modifications_log ALTER COLUMN new_values TYPE JSON USING new_values::TEXT::JSON")
    op.execute("ALTER TABLE modifications_log ALTER COLUMN old_values TYPE JSON USING old_values::TEXT::JSON")

    # --- Restore full unique index (without WHERE clause) ---
    op.drop_index(
        'uq_primary_result_per_experiment_bucket',
        table_name='experimental_results',
        if_exists=True,
    )
    op.create_index(
        'uq_primary_result_per_experiment_bucket',
        'experimental_results',
        ['experiment_fk', 'time_post_reaction_bucket_days'],
        unique=True,
    )
