"""
Data migration: deduplicate ReactorChangeRequest entries.

WHAT THIS SCRIPT DOES
---------------------
For each reactor, groups entries by consecutive runs of identical
`requested_change` text (sorted by sync_date ASC). Within each run,
keeps the earliest row (lowest sync_date) and deletes the rest.

USAGE
-----
# Preview what would be deleted (safe, no writes)
python migrate_deduplicate_change_requests.py

# Delete with interactive confirmation prompt
python migrate_deduplicate_change_requests.py --commit

# Delete without prompt (CI / headless)
python migrate_deduplicate_change_requests.py --commit --yes
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

import structlog
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from database.models.notion_sync import ReactorChangeRequest  # noqa: E402
from backend.config.settings import get_settings  # noqa: E402

log = structlog.get_logger()


def find_duplicate_ids(session: Session) -> list[int]:
    """Return IDs of all duplicate ReactorChangeRequest rows to delete.

    For each reactor, walks rows sorted by sync_date ASC. Any row whose
    requested_change equals the immediately preceding row's text is a
    duplicate — mark for deletion.
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

    by_reactor: dict[str, list] = defaultdict(list)
    for row in rows:
        by_reactor[row.reactor_label].append(row)

    to_delete: list[int] = []
    for reactor_label, entries in sorted(by_reactor.items()):
        prev_text: str | None = None
        for entry in entries:
            current_text = (entry.requested_change or "").strip()
            if current_text and current_text == prev_text:
                to_delete.append(entry.id)
            else:
                prev_text = current_text

    return to_delete


def preview(session: Session, to_delete: list[int]) -> None:
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
    settings = get_settings()
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
            log.info("change_request_dedup_complete", deleted=deleted)
            print(f"\nDeleted {deleted} duplicate row(s). Migration complete.")
            return deleted
        except Exception:
            session.rollback()
            log.exception("change_request_dedup_failed")
            print("\nError during deletion — transaction rolled back. No rows deleted.")
            raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deduplicate consecutive identical ReactorChangeRequest entries."
    )
    parser.add_argument(
        "--commit", action="store_true", default=False,
        help="Actually delete rows (default is dry-run preview only).",
    )
    parser.add_argument(
        "--yes", action="store_true", default=False,
        help="Skip the interactive confirmation prompt (use with --commit).",
    )
    args = parser.parse_args()
    run_migration(dry_run=not args.commit, skip_confirm=args.yes)


if __name__ == "__main__":
    main()
