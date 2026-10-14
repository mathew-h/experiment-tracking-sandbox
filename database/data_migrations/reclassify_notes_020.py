"""One-time backfill: give every existing note a declared type, and move the two
legacy free-text result columns into the typed notes model (issue #118, PR2).

Background
----------
Until PR1 of #118 free text about an experiment lived in four places with
nothing declaring what each was for:

* experiment_notes -- the "description" was whichever note came FIRST, and the
  three readers disagreed on "first": v_experiments ordered by created_at, the
  experiments list and dashboard by min(id). Because created_at is the
  transaction timestamp, every note a bulk upload inserted in one transaction
  shares a created_at, so the view's LIMIT 1 was arbitrary.
* experimental_results.description -- NOT NULL, required by the UI, faked by
  the Master upload for a blank cell, rendered nowhere in the app. A required
  field with no feedback loop collects filler ("Gas sample", "Liquid sample").
* experimental_results.brine_modification_description -- the only timepoint
  text with a visible affordance (the MOD badge), so real content was
  smuggled into it.

PR1 added note_type / result_id / created_by / needs_review to experiment_notes
(every existing row landed as 'observation') and made every write path write
BOTH the legacy column and a typed note. This script is the one-time
reclassification of what was already there. PR3 switches the readers to the
notes model; PR4 drops the legacy columns.

Rules, in order (deterministic; nothing is guessed)
----------------------------------------------------
Only LEGACY notes are touched: rows with created_by IS NULL. Every note PR1's
dual-write has written since carries a created_by and already has the right
type, so this script never rewrites those.

1. Per experiment, the oldest legacy note by min(id) becomes 'description'.
   min(id), not created_at -- see above for why created_at cannot order notes
   from one bulk transaction. Every other legacy note becomes 'observation'
   with result_id NULL (it already is; the UPDATE is explicit so the outcome
   does not depend on the migration default). If the experiment already holds
   a 'description' note written through PR1's API, that explicit choice is
   kept and the min(id) note stays 'observation' -- reported, not overridden.
2. A legacy note whose trimmed text lowercases to 'nan' is an artifact of the
   blank-initial_note bug PR1 fixed (docs/issues/issue-blank-initial-note-
   parses-to-nan.md), not researcher text. It is flagged needs_review and is
   NOT promoted, even when it is the oldest note. Nothing else is promoted in
   its place -- that would be a guess -- so such an experiment ends with no
   description; the report names it.
3. Every non-blank brine_modification_description becomes a note row:
   note_type='modification', result_id=er.id, experiment_fk=er.experiment_fk,
   created_at=er.created_at, created_by='reclassify_notes_020'. If a
   'modification' note with the same text already sits on that result
   (PR1's dual-write put it there), nothing is inserted.
4. experimental_results.description is classified by pattern:
   * matches ^\\s*(gas|liquid|solid|aqueous|gas\\s*\\+\\s*liquid)(\\s+sample)?\\s*$
     case-insensitively, or starts with 'Master upload — day ': discarded --
     it carries no information (the second is text this codebase generated).
   * 4b (Mat, 2026-09-09): a GC method / injection tag -- text built only from
     the tokens gas, liquid, liq, solid, DI, GC-A, GC-B, FL, Full Loop (with
     optional parenthesised method, e.g. 'Gas (GC-A)') joined by , ; . / + and,
     and containing at least one GC token -- is discarded. These say which GC
     method produced a reading; they matter to the person running the GC on
     the results sheet, not as a note on the experiment. Any extra word
     ('Cold dip tube liquid, GC-A') keeps the text out of this rule, and a
     plain fraction list with no GC token ('gas, liquid') is NOT covered.
     Reported on its own line so the audit can see the split.
   * 4c (Mat, 2026-09-09): code-generated fallbacks from the OTHER parsers --
     'Day 1.0 results', 'Analysis results for Day 7.0', 'Analysis results' --
     written by scalar_results_service.py / scalar_results.py when no
     description was supplied. Same species as 'Master upload — day'.
   * 4d (Mat, 2026-09-09): multi-fraction lists -- two or more of gas / liquid
     / liq / solid / aqueous joined by , ; / + & and, optional 'sample(s)' --
     e.g. 'gas, liquid', 'Gas and liquid sample'. Placeholders for which phases
     were sampled; the spec's rule-4 alternation only accepted one fraction.
   * 4e (Mat, 2026-09-09): the literal '0' (also '0.0'): an Excel blank read
     as zero, 75 rows all created 2026-07-23 .. 08-31.
   Each of 4b-4e is counted and listed separately in the report.
   * blank: nothing to carry.
   * otherwise: an 'observation' note on the result with needs_review=true,
     created_at=er.created_at, created_by='reclassify_notes_020'. If an
     'observation' note with the same text already sits on that result, nothing
     is inserted.
   The pattern is applied AS SPECIFIED. The report prints the most frequent
   preserved texts precisely so a human can see what the pattern did not
   catch; the pattern is not widened here to make the numbers look better.
5. Anything the rules cannot place is written with needs_review=true, never
   dropped, never guessed at. In this data set that is exactly the rule-2 and
   rule-4 rows; the report's last line is the total review queue.

Idempotent: re-running after --apply finds nothing to promote (no legacy note
lacks a type decision it already has) and inserts no duplicate result notes.

Legacy columns are NOT cleared here. Power BI reads them until PR3, and PR4
drops them.

Usage:
    # Dry run (preview only, no writes) -- the report Mat audits
    python database/data_migrations/reclassify_notes_020.py

    # Apply (only after the dry-run report has been audited)
    python database/data_migrations/reclassify_notes_020.py --apply

    # Against a specific database (defaults to $DATABASE_URL, then the dev DB)
    DATABASE_URL=postgresql://... python database/data_migrations/reclassify_notes_020.py

Frozen (issue #122 PR-D, 2026-10-14)
------------------------------------
The columns this script read were dropped by Alembic b8c4e2d7f9a1. The module
now refuses to run (exit 3); the rules above are kept verbatim as the record of
how the 'reclassify_notes_020' notes and the review queue were produced. Last
runnable version: `git show 75fc269:database/data_migrations/reclassify_notes_020.py`.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect
from sqlalchemy.orm import Session

SOURCE_TAG = "reclassify_notes_020"
DROP_REVISION = "b8c4e2d7f9a1"
LAST_RUNNABLE_COMMIT = "75fc269"
MIGRATION_PATH = "database/data_migrations/reclassify_notes_020.py"
_LEGACY_COLUMNS = ("description", "brine_modification_description", "has_brine_modification")

_FROZEN = (
    f"reclassify_notes_020 is frozen: the experimental_results columns it read "
    f"were dropped by Alembic {DROP_REVISION} (issue #122 PR-D) after the backfill "
    f"had been applied on production and its review queue emptied (0 rows on 2026-10-09). "
    f"The notes with created_by = '{SOURCE_TAG}' are the record; the rules are in this "
    f"module's docstring. The last runnable version is "
    f"`git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}` and applies only to a database "
    f"restored from a backup taken before {DROP_REVISION}."
)


def _legacy_columns_present(db: Session) -> bool:
    names = {c["name"] for c in inspect(db.get_bind()).get_columns("experimental_results")}
    return any(col in names for col in _LEGACY_COLUMNS)


def refuse_to_run(db: Session) -> None:
    """Always raise RuntimeError with the frozen-script message.

    Raised whether or not the columns exist: when they are gone (every database
    at or past DROP_REVISION) the message says why; when they are still present
    (a pre-PR-D restore) the backfill logic is no longer in this file, so the
    message points at the commit that holds it.
    """
    state = (
        "still present here (a pre-PR-D restore?)" if _legacy_columns_present(db) else "absent here"
    )
    raise RuntimeError(f"{_FROZEN} The legacy columns are {state}.")


def main(apply: bool) -> None:  # `apply` is unused: kept so the historical CLI shape still parses
    from database import get_db

    db = next(get_db())
    try:
        refuse_to_run(db)
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
