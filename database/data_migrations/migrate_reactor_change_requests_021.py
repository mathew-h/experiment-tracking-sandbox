"""FROZEN (issue #122 PR-E E2, 2026-10-09). The source table was dropped by
Alembic a7d3e9f1c2b4 after this script's production run on 2026-10-09: 357
rows, 331 converted, 26 orphaned. The conversion logic was removed with the
model it depended on; the last runnable version is
    git show 32da995:database/data_migrations/migrate_reactor_change_requests_021.py
and only makes sense against a database restored from a backup taken before
a7d3e9f1c2b4. Running this file now exits 3 with that message. Everything
below the banner is kept as the record of where the
created_by = 'migrate_change_requests_021' notes came from.

One-time backfill: convert reactor_change_requests rows into dated
'modification' notes (issue #122, PR-B; phase-2 spec decisions 1, 2, 9-11).

Background
----------
The dashboard reactor card's "Reactor Modification" form wrote to
reactor_change_requests, a table the retired Notion sync created (one row per
reactor per date, upserted). Typed experiment notes (issue #118) made that a
second, disconnected home for the same fact: v_dim_timepoints.modification_note
read only notes, so Power BI and the card disagreed. PR-B gives experiment_notes
an event_date anchor and makes the card write 'modification' notes; this script
moves the existing rows across. Nothing is deleted from reactor_change_requests
-- dropping the table is a separately authorized follow-up (PR-E2).

Rules, in id order (deterministic; nothing is guessed)
-------------------------------------------------------
1. experiment_id IS NULL -> ORPHANED, reported, not converted. The column is an
   FK to experiments.experiment_id with ON DELETE SET NULL, so NULL means the
   experiment was deleted after the row was written, or a Notion import never
   matched one. There is no string to resolve; guessing an experiment from the
   reactor label would attribute a modification to whoever occupies the slot
   today.
2. A non-NULL experiment_id resolves EXACTLY against experiments.experiment_id
   (the FK guarantees the match). No fuzzy matching, no _id_match.normalize_id.
3. requested_change blank after strip -> BLANK, reported, not converted.
4. Otherwise the row becomes ONE note via backend.services.notes.add_note:
   note_type='modification', event_date=sync_date, result_id NULL,
   note_text=requested_change.strip(), created_by=SOURCE_TAG,
   created_at=row.created_at. Dashboard-typed and Notion-imported rows convert
   alike -- both record a real modification. reactor_label is NOT carried onto
   the note (decision 2: the card knows its slot); the whole original row is
   snapshotted to ModificationsLog(modified_table='reactor_change_requests',
   modification_type='update', old_values=<row>, new_values={'note_id': id},
   experiment_fk=<exp.id>) so label, Notion status and page id are recoverable.
   experiment_fk is set on purpose: these snapshots belong to the experiment
   and die with it.
5. Idempotent. A row is ALREADY CONVERTED when its ModificationsLog snapshot
   exists (modified_table='reactor_change_requests', old_values.id = the row
   id) -- this survives later edits or deletion of the note -- or, failing
   that, when a note with the same experiment_fk, event_date, note_text and
   created_by=SOURCE_TAG exists. Two source rows sharing (experiment, date,
   text) -- possible only under two different reactor_labels, because of the
   table's unique key -- COLLAPSE into one note; the second is reported as
   collapsed, never doubled or dropped silently.
6. Informational: how many convertible rows carry a reactor_label that differs
   from the experiment's current experimental_conditions.reactor_slot. A
   difference is expected when an experiment moved reactors; it is reported so
   Mat can judge whether the label must be kept (decision 2's open question).

Usage (historical)
------------------
    PYTHONPATH=. python database/data_migrations/migrate_reactor_change_requests_021.py          # dry run
    PYTHONPATH=. python database/data_migrations/migrate_reactor_change_requests_021.py --apply  # after Mat's audit

Reports: docs/issues/migrate-change-requests-021-dryrun-2026-09-24.md (dev-mirror
dry run and apply, and the production run of 2026-10-09).
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect
from sqlalchemy.orm import Session

SOURCE_TAG = "migrate_change_requests_021"
SOURCE_TABLE = "reactor_change_requests"
DROP_REVISION = "a7d3e9f1c2b4"
LAST_RUNNABLE_COMMIT = "32da995"
MIGRATION_PATH = "database/data_migrations/migrate_reactor_change_requests_021.py"

_FROZEN = (
    f"migrate_reactor_change_requests_021 is frozen: its source table "
    f"{SOURCE_TABLE} was dropped by Alembic {DROP_REVISION} (issue #122 PR-E E2) "
    f"after the production run of 2026-10-09 (357 rows, 331 converted, 26 orphaned). "
    f"The {SOURCE_TAG} notes and their modifications_log snapshots are the record. "
    f"The last runnable version is `git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}` "
    f"and applies only to a database restored from a backup taken before {DROP_REVISION}."
)


def check_source_table(db: Session) -> None:
    """Raise RuntimeError with the frozen-script message.

    Raised whether or not the table exists: when it is gone (every database
    at or past DROP_REVISION) the message says why; when it is still present
    (a pre-E2 restore) the conversion logic is no longer in this file, so the
    message points at the commit that holds it.
    """
    present = inspect(db.get_bind()).has_table(SOURCE_TABLE)
    state = "still present here (a pre-E2 restore?)" if present else "absent here"
    raise RuntimeError(f"{_FROZEN} {SOURCE_TABLE} is {state}.")


def main(apply: bool) -> None:  # `apply` is unused: kept so the historical CLI shape still parses
    from database import get_db

    db = next(get_db())
    try:
        check_source_table(db)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(3)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="(historical) commit changes")
    args = parser.parse_args()
    main(apply=args.apply)
