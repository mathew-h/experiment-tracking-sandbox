"""unique conditions per experiment

Revision ID: 00063a5dd6a8
Revises: 1c1ef9b555e0
Create Date: 2026-08-05 09:26:14.867266

ExperimentalConditions is 1:1 with Experiment. That was assumed by the
experiments list endpoint, the delete snapshot and the v_experiments /
v_experiment_conditions Power BI views, and enforced nowhere -- so one duplicate
row 500'd the experiments page, duplicated the Power BI dimension key and made
the experiment undeletable (issue #109 follow-up).

This migration FAILS LOUDLY if duplicates remain, rather than skipping: run
database/data_migrations/dedupe_conditions_and_backfill_ids_018.py --apply
first. The lab PC came up through this chain, so it is the path that matters.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '00063a5dd6a8'
down_revision: Union[str, None] = '1c1ef9b555e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    duplicates = conn.execute(sa.text("""
        SELECT experiment_fk, COUNT(*) AS n
        FROM experimental_conditions
        GROUP BY experiment_fk HAVING COUNT(*) > 1
        ORDER BY experiment_fk
    """)).all()
    if duplicates:
        listed = ", ".join(f"experiment_fk={fk} ({n} rows)" for fk, n in duplicates)
        raise RuntimeError(
            "Cannot add uq_conditions_experiment_fk: duplicate conditions rows "
            f"still present -- {listed}. Run "
            "database/data_migrations/dedupe_conditions_and_backfill_ids_018.py "
            "--apply first."
        )
    op.create_unique_constraint(
        'uq_conditions_experiment_fk', 'experimental_conditions', ['experiment_fk']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'uq_conditions_experiment_fk', 'experimental_conditions', type_='unique'
    )
