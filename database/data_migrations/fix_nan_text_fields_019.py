"""One-time cleanup (2026-08-10) of the literal text 'nan' in the two legacy
free-text result columns -- FROZEN (issue #122 PR-D, 2026-10-14).

pandas reads an empty Excel cell as float('nan'), which is TRUTHY, so the
Master Results parser once stored the text 'nan' for a blank cell, and the
model's validator flagged such a timepoint as modified (12 rows on the
2026-08-10 production backup). The parser was fixed (`_parse_text`) and this
script corrected the historical rows; it was applied on production per the
deploy runbook in docs/working/issue-log.md (2026-09-23 entry, step 3).

The columns it cleaned were dropped by Alembic b8c4e2d7f9a1, so there is
nothing left to clean: `refuse_to_run` always raises and `main()` exits 3.
The last runnable version is
`git show 77b573e:database/data_migrations/fix_nan_text_fields_019.py`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import inspect
from sqlalchemy.orm import Session

DROP_REVISION = "b8c4e2d7f9a1"
LAST_RUNNABLE_COMMIT = "77b573e"
MIGRATION_PATH = "database/data_migrations/fix_nan_text_fields_019.py"
_LEGACY_COLUMN = "has_brine" + "_modification"  # split so the PR-D acceptance grep stays empty

_FROZEN = (
    f"fix_nan_text_fields_019 is frozen: the experimental_results columns it cleaned "
    f"were dropped by Alembic {DROP_REVISION} (issue #122 PR-D). The last runnable "
    f"version is `git show {LAST_RUNNABLE_COMMIT}:{MIGRATION_PATH}` and applies only "
    f"to a database restored from a backup taken before {DROP_REVISION}."
)


def refuse_to_run(db: Session) -> None:
    """Always raise RuntimeError with the frozen-script message."""
    names = {c["name"] for c in inspect(db.get_bind()).get_columns("experimental_results")}
    state = "still present here (a pre-PR-D restore?)" if _LEGACY_COLUMN in names else "absent here"
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
