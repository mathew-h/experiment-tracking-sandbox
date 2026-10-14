"""Drop the legacy result note columns (issue #122, PR-D).

experimental_results.description, brine_modification_description and
has_brine_modification leave the schema. Since issue #118 PR3 nothing read
them: the MOD badge, GET /experiments/{id}/results, v_dim_timepoints
(modification_note) and v_results_scalar (sampling_description removed) all
read experiment_notes. PR-D removed the last writers (the dual-writes in
POST /api/results, Master Results, Timepoint Modifications; the parser
fallbacks 'Master upload — day N', 'Day N results', 'Analysis results for
Day N'). The 020 backfill moved the researcher-written content into
observation / modification notes; its review queue was emptied on production
(0 rows on 2026-10-09, reported by Mat). Mat pre-authorized the three drops
on 2026-09-23 (phase-2 spec §2 item 3) -- the §7 sign-off for this
non-additive migration.

No view references the three columns (database/event_listeners.py), so the
DROPs need no CASCADE and no view is recreated here.

downgrade() recreates the three columns NULLABLE and the index
ix_experimental_results_has_brine_modification. It restores no data: the
text lives in experiment_notes (created_by = 'reclassify_notes_020',
'master_bulk_upload', a researcher's email, ...). description was NOT NULL
(87f4f47b5a11) and has_brine_modification NOT NULL DEFAULT false
(f59050b45fc4); a downgrade cannot honor those on existing rows without
inventing text, so it does not.

Revision ID: b8c4e2d7f9a1
Revises: a7d3e9f1c2b4
Create Date: 2026-10-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c4e2d7f9a1"
down_revision: Union[str, None] = "a7d3e9f1c2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "experimental_results"
INDEX = "ix_experimental_results_has_brine_modification"


def upgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, "has_brine_modification")
    op.drop_column(TABLE, "brine_modification_description")
    op.drop_column(TABLE, "description")


def downgrade() -> None:
    op.add_column(TABLE, sa.Column("description", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("brine_modification_description", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("has_brine_modification", sa.Boolean(), nullable=True))
    op.create_index(INDEX, TABLE, ["has_brine_modification"], unique=False)
