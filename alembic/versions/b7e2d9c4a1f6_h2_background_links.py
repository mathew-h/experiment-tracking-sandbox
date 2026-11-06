"""H2 background links table (#144).

Additive: new table h2_background_links mapping a sample base experiment to the
background vial set (or single stem) whose H2 is subtracted in reporting.

downgrade() drops v_results_h2_bkg_adjusted_rollup and v_results_h2_bkg_adjusted
BEFORE the table: database/event_listeners.py recreates those views (which read
h2_background_links) at API import, so a bare drop_table would fail with
"cannot drop table ... because other objects depend on it". The rollup view
depends on the adjusted view, so it goes first.

Revision ID: b7e2d9c4a1f6
Revises: a1c5e8f2b9d3
Create Date: 2026-11-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2d9c4a1f6"
down_revision: Union[str, None] = "a1c5e8f2b9d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "h2_background_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("base_experiment_id", sa.String(), nullable=False),
        sa.Column("background_base_id", sa.String(), nullable=True),
        sa.Column("background_stem_id", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("base_experiment_id"),
        sa.CheckConstraint(
            "num_nonnulls(background_base_id, background_stem_id) = 1",
            name="ck_h2_background_links_one_ref",
        ),
        sa.CheckConstraint(
            "background_base_id IS DISTINCT FROM base_experiment_id",
            name="ck_h2_background_links_not_self",
        ),
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_results_h2_bkg_adjusted_rollup")
    op.execute("DROP VIEW IF EXISTS v_results_h2_bkg_adjusted")
    op.drop_table("h2_background_links")
