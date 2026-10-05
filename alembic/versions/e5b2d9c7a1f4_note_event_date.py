"""experiment_notes.event_date and a relaxed ck_note_scope (issue #122, PR-B).

A reactor modification is a 'modification' note anchored to a result OR to a
calendar date (design decision 1 of the phase-2 spec). Until now ck_note_scope
required every 'modification' to carry a result_id, which cannot represent the
dashboard's "what was done to this reactor on <date>" entries -- those lived in
the Notion-era reactor_change_requests table, which PR-B retires.

* ADD COLUMN event_date DATE NULL + ix_experiment_notes_event_date.
* ck_note_scope becomes:
    description  => result_id IS NULL
    modification => result_id IS NOT NULL OR event_date IS NOT NULL
    result_note  => result_id IS NOT NULL
    observation  => anything
* v_notes gains event_date (recreated here AND in database/event_listeners.py,
  house pattern from c4d8f1a2b6e7, so Power BI is right after the nightly
  `alembic upgrade head` even before the API restarts).

Downgrade restores the old CHECK and drops the column, but REFUSES (RuntimeError
naming the count) while any 'modification' row is anchored by event_date alone:
such rows would violate the old CHECK and the alternative -- deleting them --
is data loss a downgrade must not decide on its own (house pattern from
00063a5dd6a8).

Revision ID: e5b2d9c7a1f4
Revises: c4d8f1a2b6e7
Create Date: 2026-09-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5b2d9c7a1f4"
down_revision: Union[str, None] = "c4d8f1a2b6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCOPE_CHECK_OLD = (
    "(note_type = 'description' AND result_id IS NULL) OR "
    "(note_type IN ('modification', 'result_note') AND result_id IS NOT NULL) OR "
    "(note_type = 'observation')"
)
_SCOPE_CHECK_NEW = (
    "(note_type = 'description' AND result_id IS NULL) OR "
    "(note_type = 'modification' AND (result_id IS NOT NULL OR event_date IS NOT NULL)) OR "
    "(note_type = 'result_note' AND result_id IS NOT NULL) OR "
    "(note_type = 'observation')"
)

_V_NOTES_OLD = """
    CREATE VIEW v_notes AS
    SELECT
        n.id                 AS note_id,
        e.experiment_id,
        n.result_id,
        n.note_type::text    AS note_type,
        n.note_text,
        n.created_at,
        n.created_by,
        n.needs_review
    FROM experiment_notes n
    JOIN experiments e ON e.id = n.experiment_fk
"""
_V_NOTES_NEW = """
    CREATE VIEW v_notes AS
    SELECT
        n.id                 AS note_id,
        e.experiment_id,
        n.result_id,
        n.event_date,
        n.note_type::text    AS note_type,
        n.note_text,
        n.created_at,
        n.created_by,
        n.needs_review
    FROM experiment_notes n
    JOIN experiments e ON e.id = n.experiment_fk
"""


def upgrade() -> None:
    op.add_column("experiment_notes", sa.Column("event_date", sa.Date(), nullable=True))
    op.create_index("ix_experiment_notes_event_date", "experiment_notes", ["event_date"])
    op.drop_constraint("ck_note_scope", "experiment_notes", type_="check")
    op.create_check_constraint("ck_note_scope", "experiment_notes", _SCOPE_CHECK_NEW)
    op.execute("DROP VIEW IF EXISTS v_notes CASCADE")
    op.execute(_V_NOTES_NEW)


def downgrade() -> None:
    conn = op.get_bind()
    dated_only = conn.execute(sa.text(
        "SELECT count(*) FROM experiment_notes "
        "WHERE note_type = 'modification' AND result_id IS NULL AND event_date IS NOT NULL"
    )).scalar_one()
    if dated_only:
        raise RuntimeError(
            f"Cannot downgrade e5b2d9c7a1f4: {dated_only} 'modification' note(s) are anchored "
            "only by event_date and would violate the pre-PR-B ck_note_scope. Retype or "
            "delete them first: SELECT id FROM experiment_notes WHERE note_type = 'modification' "
            "AND result_id IS NULL AND event_date IS NOT NULL"
        )
    op.execute("DROP VIEW IF EXISTS v_notes CASCADE")
    op.execute(_V_NOTES_OLD)
    op.drop_constraint("ck_note_scope", "experiment_notes", type_="check")
    op.create_check_constraint("ck_note_scope", "experiment_notes", _SCOPE_CHECK_OLD)
    op.drop_index("ix_experiment_notes_event_date", table_name="experiment_notes")
    op.drop_column("experiment_notes", "event_date")
