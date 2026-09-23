"""Typed experiment notes: note_type, result_id, created_by, needs_review (issue #118, PR1).

Additive only. Every existing experiment_notes row lands as note_type =
'observation' with result_id NULL, which satisfies the scope CHECK and never
touches the partial unique index, so this migration cannot fail on existing
data. PR2's database/data_migrations/reclassify_notes_020.py is what promotes
the right row per experiment to 'description' and migrates the legacy
experimental_results text columns into note rows -- deliberately a separate,
dry-run-first step so the reclassification can be audited before it is applied.

What the constraints guarantee (enforced by Postgres, not by app code):
  * uq_one_description_per_experiment -- at most one 'description' note per
    experiment. Partial unique index, so it never bites the other three types.
  * uq_results_experiment_fk_id + fk_note_result_same_experiment -- a note that
    names a result_id must belong to the same experiment as that result. The
    composite FK uses MATCH SIMPLE, so a NULL result_id (every experiment-level
    note) is not checked at all -- intended. ON DELETE CASCADE removes a
    result's notes with the result.
  * ck_note_scope -- 'description' is never result-scoped; 'modification' and
    'result_note' always are; 'observation' may be either (scope-free by design).

Revision ID: b7e2c9a41d05
Revises: 5840d41bf18d
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b7e2c9a41d05"
down_revision = "5840d41bf18d"
branch_labels = None
depends_on = None

NOTE_TYPES = ("description", "modification", "observation", "result_note")

_SCOPE_CHECK = (
    "(note_type = 'description' AND result_id IS NULL) OR "
    "(note_type IN ('modification', 'result_note') AND result_id IS NOT NULL) OR "
    "(note_type = 'observation')"
)


def upgrade() -> None:
    bind = op.get_bind()
    # create_type=False on the column type below: the type is created here,
    # once, with checkfirst so a partially-applied run can be resumed.
    note_type = postgresql.ENUM(*NOTE_TYPES, name="note_type", create_type=False)
    note_type.create(bind, checkfirst=True)

    op.add_column(
        "experiment_notes",
        sa.Column("note_type", note_type, nullable=False, server_default="observation"),
    )
    op.add_column("experiment_notes", sa.Column("result_id", sa.Integer(), nullable=True))
    op.add_column("experiment_notes", sa.Column("created_by", sa.String(), nullable=True))
    op.add_column(
        "experiment_notes",
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_index(
        "uq_one_description_per_experiment",
        "experiment_notes",
        ["experiment_fk"],
        unique=True,
        postgresql_where=sa.text("note_type = 'description'"),
    )
    op.create_unique_constraint(
        "uq_results_experiment_fk_id", "experimental_results", ["experiment_fk", "id"]
    )
    op.create_foreign_key(
        "fk_note_result_same_experiment",
        "experiment_notes",
        "experimental_results",
        ["experiment_fk", "result_id"],
        ["experiment_fk", "id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint("ck_note_scope", "experiment_notes", _SCOPE_CHECK)
    op.create_index("ix_experiment_notes_result_id", "experiment_notes", ["result_id"])
    op.create_index("ix_experiment_notes_scope", "experiment_notes", ["experiment_fk", "note_type"])


def downgrade() -> None:
    op.drop_index("ix_experiment_notes_scope", table_name="experiment_notes")
    op.drop_index("ix_experiment_notes_result_id", table_name="experiment_notes")
    op.drop_constraint("ck_note_scope", "experiment_notes", type_="check")
    op.drop_constraint("fk_note_result_same_experiment", "experiment_notes", type_="foreignkey")
    op.drop_constraint("uq_results_experiment_fk_id", "experimental_results", type_="unique")
    op.drop_index("uq_one_description_per_experiment", table_name="experiment_notes")
    op.drop_column("experiment_notes", "needs_review")
    op.drop_column("experiment_notes", "created_by")
    op.drop_column("experiment_notes", "result_id")
    op.drop_column("experiment_notes", "note_type")
    postgresql.ENUM(name="note_type").drop(op.get_bind(), checkfirst=True)
