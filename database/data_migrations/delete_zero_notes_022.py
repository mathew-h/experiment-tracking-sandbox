"""One-time cleanup: delete the '0' notes the Master Results parser wrote from
XLOOKUP zero cells (zero-note-cells fix C; see docs/issues/issue-zero-note-cells.md,
section "Fix" C and the data table under "Impact").

Background
----------
A blank cell fed through an XLOOKUP comes back as the number 0, and the Master
Results parser stored it as a note with text '0'. Fixes A and B stop the parser
writing them; this script removes the ones already stored.

Rules (exact match, no LIKE)
----------------------------
TARGETS (deleted, one ModificationsLog snapshot each):
    note_type IN ('modification', 'observation')
    AND note_text = '0'
    AND created_by = 'master_bulk_upload'

REPORTED ONLY, never touched:
    * joined-zero notes ('0' as one of several '; '-separated parts)
    * exact '0' with another non-NULL author, or of type description/result_note
    * exact '0' with created_by IS NULL
    * 'nan' notes (a separate, already-handled problem)

Audit: each delete writes ModificationsLog(modification_type='delete',
modified_table='experiment_notes', modified_by='delete_zero_notes_022',
old_values={id, note_text, note_type, result_id, created_by, needs_review},
new_values=None). One transaction, one commit, in main().

Why this is not an Alembic migration
------------------------------------
It deletes rows, so a downgrade could not restore them; it must be audited by
a human before applying (dry run first); and it is a one-off against data, not
a schema change. The ModificationsLog snapshots are the recovery path.

Idempotent: a second --apply finds no targets and deletes nothing.

Deploy order: fixes A and B (parser) must be deployed first, otherwise the next
Master Results upload re-creates the notes.

Usage
-----
    # Dry run (default): prints the report, writes nothing
    PYTHONPATH=. python database/data_migrations/delete_zero_notes_022.py

    # Apply -- ONLY after Mat has audited the dry-run report
    PYTHONPATH=. python database/data_migrations/delete_zero_notes_022.py --apply
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from database import get_db  # noqa: E402
from database.models.enums import NoteType  # noqa: E402
from database.models.experiments import ExperimentNotes, ModificationsLog  # noqa: E402

SOURCE_TAG = "delete_zero_notes_022"
TARGET_AUTHOR = "master_bulk_upload"


@dataclass
class Plan:
    targets: list[ExperimentNotes] = field(default_factory=list)
    joined_zero: list[ExperimentNotes] = field(default_factory=list)
    other_author_zero: list[ExperimentNotes] = field(default_factory=list)
    null_author_zero: list[ExperimentNotes] = field(default_factory=list)
    nan_notes: list[ExperimentNotes] = field(default_factory=list)


def _is_joined_zero(text_: Optional[str]) -> bool:
    if text_ is None or text_ == "0":
        return False
    return "0" in [p.strip() for p in text_.split(";")]


def build_plan(db: Session) -> Plan:
    """Read-only. Everything --apply will do is decided here."""
    plan = Plan()
    target_types = (NoteType.modification, NoteType.observation)
    rows = db.execute(select(ExperimentNotes).order_by(ExperimentNotes.id)).scalars().all()
    for n in rows:
        text_ = n.note_text
        if text_ == "0":
            if n.created_by is None:
                plan.null_author_zero.append(n)
            elif n.created_by == TARGET_AUTHOR and n.note_type in target_types:
                plan.targets.append(n)
            else:
                plan.other_author_zero.append(n)
        elif _is_joined_zero(text_):
            plan.joined_zero.append(n)
        elif text_ is not None and text_.strip().lower() == "nan":
            plan.nan_notes.append(n)
    return plan


def _short(text_: Optional[str], width: int = 60) -> str:
    t = (text_ or "").replace("\n", " ")
    return t if len(t) <= width else t[: width - 1] + "…"


def _ntype(n: ExperimentNotes) -> str:
    return n.note_type.value if hasattr(n.note_type, "value") else str(n.note_type)


def print_report(plan: Plan) -> None:
    p = print
    buckets = [
        ("targets (deleted on --apply)", plan.targets),
        ("joined-zero (report only)", plan.joined_zero),
        ("other-author / other-type zero (report only)", plan.other_author_zero),
        ("NULL-author zero (report only)", plan.null_author_zero),
        ("nan notes (report only)", plan.nan_notes),
    ]
    p("## delete_zero_notes_022 -- report\n")
    p("| bucket | count |")
    p("|---|---|")
    for name, items in buckets:
        p(f"| {name} | {len(items)} |")
    p("")
    by_type: dict[str, int] = {}
    for n in plan.targets:
        by_type[_ntype(n)] = by_type.get(_ntype(n), 0) + 1
    p("Targets by note_type: " + (", ".join(f"{k}={v}" for k, v in sorted(by_type.items())) or "none"))
    for name, items in buckets:
        p(f"\n### {name}")
        if not items:
            p("(none)")
            continue
        p("id | experiment_id | note_type | result_id | created_by | note_text")
        for n in items:
            p(f"{n.id} | {n.experiment_id} | {_ntype(n)} | {n.result_id} | {n.created_by} | {_short(n.note_text)}")


def apply_plan(db: Session, plan: Plan) -> list[int]:
    """Snapshot then delete every target. Flushes, does NOT commit."""
    deleted: list[int] = []
    for n in plan.targets:
        db.add(ModificationsLog(
            experiment_id=n.experiment_id,
            experiment_fk=n.experiment_fk,
            modified_by=SOURCE_TAG,
            modification_type="delete",
            modified_table="experiment_notes",
            old_values={
                "id": n.id,
                "note_text": n.note_text,
                "note_type": _ntype(n),
                "result_id": n.result_id,
                "created_by": n.created_by,
                "needs_review": n.needs_review,
            },
            new_values=None,
        ))
        deleted.append(n.id)
        db.delete(n)
    db.flush()
    return deleted


def after_counts(db: Session) -> dict:
    return {
        "notes_total": db.execute(select(func.count()).select_from(ExperimentNotes)).scalar_one(),
        "targets": len(build_plan(db).targets),
        "snapshots_by_022": db.execute(
            select(func.count()).select_from(ModificationsLog)
            .where(ModificationsLog.modified_by == SOURCE_TAG)
        ).scalar_one(),
    }


def main(apply: bool) -> None:
    db = next(get_db())
    try:
        before = after_counts(db)
        plan = build_plan(db)
        print_report(plan)
        print("\nbefore:", before)
        if not apply:
            print("\nDry run — pass --apply to commit changes.")
            return
        ids = apply_plan(db, plan)
        db.commit()
        after = after_counts(db)
        print("after: ", after)
        if (len(ids) != len(plan.targets)
                or after["targets"] != 0
                or after["notes_total"] != before["notes_total"] - len(plan.targets)):
            print(f"WARNING: deleted {len(ids)}, planned {len(plan.targets)}; after {after}",
                  file=sys.stderr)
            sys.exit(2)
        print(f"\nApplied. {len(ids)} notes deleted (matches the dry-run plan).")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry run)")
    args = parser.parse_args()
    main(apply=args.apply)
