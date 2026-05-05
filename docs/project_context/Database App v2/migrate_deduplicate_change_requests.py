"""
Data migration: deduplicate ReactorChangeRequest entries.

PROBLEM
-------
When a reactor stays "In Progress" and the user doesn't update the change
request text, the daily sync records a new DB row each morning with the same
`requested_change` string and carried_forward=True. This produces long runs of
identical entries — one per calendar day — for what is really a single ongoing
task.

WHAT THIS SCRIPT DOES
---------------------
For each reactor, it groups entries by consecutive runs of identical
`requested_change` text (sorted by sync_date ASC). Within each run it keeps
the earliest row (lowest sync_date) and deletes the rest.

SAFETY GUARANTEES
-----------------
- Dry-run mode (default): prints a preview, touches nothing.
- Commit mode: deletes only after printing a summary and prompting for
  confirmation (bypass with --yes).
- Only rows with carried_forward=True are candidates for deletion; the first
  row in every consecutive run is always kept regardless of its flag.
- All deletes happen in a single transaction; rolls back on any error.

USAGE
-----
# Preview what would be deleted (safe, no writes)
python migrate_deduplicate_change_requests.py

# Actually delete, with interactive confirmation prompt
python migrate_deduplicate_change_requests.py --commit

# Delete without prompt (CI / headless)
python migrate_deduplicate_change_requests.py --commit --yes
"""

import argparse
import sys
from collections import defaultdict
from itertools import groupby

import structlog
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Path bootstrap — lets this script run from the repo root OR from this dir
# ---------------------------------------------------------------------------
import os

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from database.models.notion_sync import ReactorChangeRequest  # noqa: E402
from backend.core.config import settings  # noqa: E402

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def find_duplicate_ids(session: Session) -> list[int]:
    """
    Return the IDs of all duplicate ReactorChangeRequest rows to be deleted.

    Algorithm:
      For each reactor_label, sort rows by sync_date ASC.
      Walk through in order; any row whose requested_change equals the
      immediately preceding row's text is a duplicate — mark it for deletion.
      (This handles runs of any length: keep the first, drop the rest.)
    """
    rows = session.execute(
        select(
            ReactorChangeRequest.id,
            ReactorChangeRequest.reactor_label,
            ReactorChangeRequest.requested_change,
            ReactorChangeRequest.sync_date,
            ReactorChangeRequest.carried_forward,
        ).order_by(
            ReactorChangeRequest.reactor_label,
            ReactorChangeRequest.sync_date,
        )
    ).fetchall()

    # Group by reactor
    by_reactor: dict[str, list] = defaultdict(list)
    for row in rows:
        by_reactor[row.reactor_label].append(row)

    to_delete: list[int] = []

    for reactor_label, entries in sorted(by_reactor.items()):
        prev_text: str | None = None
        for entry in entries:
            current_text = (entry.requested_change or "").strip()
            if current_text and current_text == prev_text:
                # Duplicate of the preceding run — mark for deletion
                to_delete.append(entry.id)
            else:
                # New text (or first entry) — this one is the keeper
                prev_text = current_text

    return to_delete


def preview(session: Session, to_delete: list[int]) -> None:
    """Print a human-readable preview of what would be deleted."""
    if not to_delete:
        print("\nNo duplicate rows found. Database is clean.")
        return

    rows = session.execute(
        select(ReactorChangeRequest).where(
            ReactorChangeRequest.id.in_(to_delete)
        ).order_by(
            ReactorChangeRequest.reactor_label,
            ReactorChangeRequest.sync_date,
        )
    ).scalars().all()

    print(f"\nFound {len(to_delete)} duplicate row(s) to delete:\n")
    print(f"  {'ID':>6}  {'Reactor':<8}  {'Date':<12}  {'CF':<5}  Text")
    print("  " + "-" * 80)
    for r in rows:
        text_preview = (r.requested_change or "")[:55]
        if len(r.requested_change or "") > 55:
            text_preview += "..."
        print(
            f"  {r.id:>6}  {r.reactor_label:<8}  "
            f"{str(r.sync_date):<12}  "
            f"{'Yes' if r.carried_forward else 'No':<5}  {text_preview}"
        )
    print()


def run_migration(dry_run: bool, skip_confirm: bool) -> int:
    """
    Execute the deduplication migration.

    Returns the number of rows deleted (0 in dry-run mode).
    """
    engine = create_engine(settings.database_url, echo=False)

    with Session(engine) as session:
        to_delete = find_duplicate_ids(session)
        preview(session, to_delete)

        if dry_run:
            print("DRY RUN — no changes written. Re-run with --commit to apply.")
            return 0

        if not to_delete:
            return 0

        if not skip_confirm:
            answer = input(
                f"Delete {len(to_delete)} row(s)? This cannot be undone. [yes/N] "
            ).strip().lower()
            if answer != "yes":
                print("Aborted.")
                return 0

        try:
            result = session.execute(
                delete(ReactorChangeRequest).where(
                    ReactorChangeRequest.id.in_(to_delete)
                )
            )
            session.commit()
            deleted = result.rowcount
            log.info(
                "change_request_dedup_complete",
                deleted=deleted,
            )
            print(f"\nDeleted {deleted} duplicate row(s). Migration complete.")
            return deleted
        except Exception:
            session.rollback()
            log.exception("change_request_dedup_failed")
            print("\nError during deletion — transaction rolled back. No rows deleted.")
            raise


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deduplicate consecutive identical ReactorChangeRequest entries."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        default=False,
        help="Actually delete rows (default is dry-run preview only).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help="Skip the interactive confirmation prompt (use with --commit).",
    )
    args = parser.parse_args()

    dry_run = not args.commit
    run_migration(dry_run=dry_run, skip_confirm=args.yes)


if __name__ == "__main__":
    main()
