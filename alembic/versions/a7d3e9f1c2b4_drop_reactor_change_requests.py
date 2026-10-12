"""Drop reactor_change_requests (issue #122, PR-E E2).

The Notion-era reactor change-request table leaves the schema. Its rows were
converted to dated 'modification' notes by
database/data_migrations/migrate_reactor_change_requests_021.py -- production
run 2026-10-09: 357 rows, 331 converted, 26 orphaned (rows whose experiment_id
was already NULL); one ModificationsLog snapshot per converted row holds the
full original row. The code that read and wrote the table left in PR-E E1
(#127). Mat authorized this drop on 2026-10-09 (phase-2 spec §2 -- the §7
sign-off for a non-additive migration).

History of the table, kept here as the shape downgrade() recreates:
  9c358174ea54  create_table; FK experiment_id -> experiments.experiment_id
                ON DELETE SET NULL; unique uq_change_request_reactor_date
  13fc77a07865  notion_status and notion_page_id become nullable
  ca5d57c6b272  unique becomes uq_change_request_reactor_experiment_date
                on (reactor_label, experiment_id, sync_date)
None of the three is deleted.

downgrade() recreates the table EMPTY in that final shape. It restores no data:
the 26 unconverted rows exist only in a pre-drop backup (pruned after 30 days by backup.ps1); the 331 converted ones
are experiment_notes rows (created_by = 'migrate_change_requests_021') with
their originals in modifications_log.old_values.

Upgrade on a database that never had the table (one built by
Base.metadata.create_all after this revision, then stamped behind it) fails
with UndefinedTable. That is deliberate: the fresh-install path stamps head and
never runs this, and a DROP that silently no-ops would hide a stamp mistake. Recovery when the
table is already gone: `alembic stamp a7d3e9f1c2b4` -- the nightly update.ps1
aborts at `alembic upgrade head` and retries the same failure every night until
someone does this.

Revision ID: a7d3e9f1c2b4
Revises: e5b2d9c7a1f4
Create Date: 2026-10-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3e9f1c2b4"
down_revision: Union[str, None] = "e5b2d9c7a1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "reactor_change_requests"


def upgrade() -> None:
    op.drop_table(TABLE)


def downgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reactor_label", sa.String(length=10), nullable=False),
        sa.Column("experiment_id", sa.String(), nullable=True),
        sa.Column("requested_change", sa.String(), nullable=False),
        sa.Column("notion_status", sa.String(length=50), nullable=True),
        sa.Column("carried_forward", sa.Boolean(), nullable=False),
        sa.Column("sync_date", sa.Date(), nullable=False),
        sa.Column("notion_page_id", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiments.experiment_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "reactor_label", "experiment_id", "sync_date",
            name="uq_change_request_reactor_experiment_date",
        ),
    )
