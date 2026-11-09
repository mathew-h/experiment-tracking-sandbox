"""One-time reclassification: notes the bulk uploads wrote from their
Description / Observation Note column become 'result_note', not 'observation'.

Background
----------
Since issue #122 PR-D (2026-10-14) ScalarResultsService mirrored a parser's
free-text Description column into an 'observation' note on the result, signed
with the parser tag. On 2026-11-09 Mat ruled that this text is a result note:
the same type the Add Results form writes and shows as "Result Note/Sample
Description". The service now writes 'result_note'; this script moves the notes
already stored, so the next upload finds its slot (sync_result_note keys a slot
on (result_id, note_type, created_by)) and does not add a second copy.

Rules (exact match)
-------------------
TARGETS (retyped, one ModificationsLog snapshot each):
    note_type = 'observation'
    AND result_id IS NOT NULL
    AND created_by IN UPLOAD_SLOT_SIGNERS
        ('master_bulk_upload', 'scalar_results', 'quick_upload')

SKIPPED, reported:
    * a target whose result already holds a 'result_note' signed by the same
      parser (retyping it would put two notes in one slot)

REPORTED ONLY, never touched:
    * result-scoped 'observation' notes with any other author (researchers, the
      020 backfill, NULL). The 020 rows came from the dropped
      experimental_results.description column and cannot be told apart from
      researcher text, so they stay as they are.

A researcher who edited an upload note in the app re-signed it to their email
(release_upload_slot), so it is no longer a target. That is intended.

Audit: each retype writes ModificationsLog(modification_type='update',
modified_table='experiment_notes', modified_by='reclassify_upload_notes_024',
old_values={id, note_type: 'observation', result_id, created_by},
new_values={note_type: 'result_note'}). One transaction, one commit, in main().

Why this is not an Alembic migration: it changes data, not schema; it is
audited by a human from the dry run before applying; the ModificationsLog
snapshots are the way back.

Idempotent: a second --apply finds no targets.

Deploy order: the service change (uploads write 'result_note') must be deployed
first, otherwise an upload between this script and the deploy writes new
'observation' notes again.

Usage
-----
    # Dry run (default): prints the report, writes nothing
    PYTHONPATH=. python database/data_migrations/reclassify_upload_notes_024.py

    # Apply -- ONLY after Mat has audited the dry-run report
    PYTHONPATH=. python database/data_migrations/reclassify_upload_notes_024.py --apply
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from database import get_db  # noqa: E402
from database.models.enums import NoteType  # noqa: E402
from database.models.experiments import ExperimentNotes, ModificationsLog  # noqa: E402

SOURCE_TAG = "reclassify_upload_notes_024"
# Same set as backend.services.notes.UPLOAD_SLOT_SIGNERS; restated so the
# script does not import the backend package. A test pins the two together.
UPLOAD_SIGNERS = frozenset({"master_bulk_upload", "scalar_results", "quick_upload"})


@dataclass
class Plan:
    targets: list[ExperimentNotes] = field(default_factory=list)
    slot_taken: list[ExperimentNotes] = field(default_factory=list)
    other_authors: Counter = field(default_factory=Counter)


def build_plan(db: Session) -> Plan:
    """Read-only. Everything --apply will do is decided here."""
    plan = Plan()
    taken = {
        (rid, by) for rid, by in db.execute(
            select(ExperimentNotes.result_id, ExperimentNotes.created_by).where(
                ExperimentNotes.note_type == NoteType.result_note,
                ExperimentNotes.result_id.is_not(None),
                ExperimentNotes.created_by.in_(UPLOAD_SIGNERS),
            )
        )
    }
    rows = db.execute(
        select(ExperimentNotes).where(
            ExperimentNotes.note_type == NoteType.observation,
            ExperimentNotes.result_id.is_not(None),
        ).order_by(ExperimentNotes.id)
    ).scalars().all()
    for n in rows:
        if n.created_by not in UPLOAD_SIGNERS:
            plan.other_authors[n.created_by or "(NULL)"] += 1
        elif (n.result_id, n.created_by) in taken:
            plan.slot_taken.append(n)
        else:
            plan.targets.append(n)
    return plan


def _short(text_: str | None, width: int = 60) -> str:
    t = (text_ or "").replace("\n", " ")
    return t if len(t) <= width else t[: width - 1] + "…"


def print_report(plan: Plan) -> None:
    p = print
    p("## reclassify_upload_notes_024 -- report\n")
    p("| bucket | count |")
    p("|---|---|")
    p(f"| targets (retyped to result_note on --apply) | {len(plan.targets)} |")
    p(f"| skipped: parser already holds a result_note on that result | {len(plan.slot_taken)} |")
    p(f"| other-author result-scoped observations (report only) | {sum(plan.other_authors.values())} |")
    by_signer = Counter(n.created_by for n in plan.targets)
    p("\nTargets by signer: "
      + (", ".join(f"{k}={v}" for k, v in sorted(by_signer.items())) or "none"))
    p("Other authors: "
      + (", ".join(f"{k}={v}" for k, v in plan.other_authors.most_common()) or "none"))
    p("\n### skipped (slot taken)")
    if not plan.slot_taken:
        p("(none)")
    for n in plan.slot_taken:
        p(f"{n.id} | {n.experiment_id} | {n.result_id} | {n.created_by} | {_short(n.note_text)}")
    p("\n### first 25 targets")
    if not plan.targets:
        p("(none)")
    for n in plan.targets[:25]:
        p(f"{n.id} | {n.experiment_id} | {n.result_id} | {n.created_by} | {_short(n.note_text)}")


def apply_plan(db: Session, plan: Plan) -> list[int]:
    """Snapshot then retype every target. Flushes, does NOT commit."""
    changed: list[int] = []
    for n in plan.targets:
        db.add(ModificationsLog(
            experiment_id=n.experiment_id,
            experiment_fk=n.experiment_fk,
            modified_by=SOURCE_TAG,
            modification_type="update",
            modified_table="experiment_notes",
            old_values={
                "id": n.id,
                "note_type": NoteType.observation.value,
                "result_id": n.result_id,
                "created_by": n.created_by,
            },
            new_values={"note_type": NoteType.result_note.value},
        ))
        n.note_type = NoteType.result_note
        changed.append(n.id)
    db.flush()
    return changed


def counts(db: Session) -> dict:
    def n_type(t: NoteType) -> int:
        return db.execute(
            select(func.count()).select_from(ExperimentNotes).where(
                ExperimentNotes.note_type == t,
                ExperimentNotes.result_id.is_not(None),
                ExperimentNotes.created_by.in_(UPLOAD_SIGNERS),
            )
        ).scalar_one()
    return {
        "upload_observations": n_type(NoteType.observation),
        "upload_result_notes": n_type(NoteType.result_note),
        "snapshots_by_024": db.execute(
            select(func.count()).select_from(ModificationsLog)
            .where(ModificationsLog.modified_by == SOURCE_TAG)
        ).scalar_one(),
    }


def main(apply: bool) -> None:
    db = next(get_db())
    try:
        before = counts(db)
        plan = build_plan(db)
        print_report(plan)
        print("\nbefore:", before)
        if not apply:
            print("\nDry run — pass --apply to commit changes.")
            return
        ids = apply_plan(db, plan)
        db.commit()
        after = counts(db)
        print("after: ", after)
        if (len(ids) != len(plan.targets)
                or after["upload_result_notes"] != before["upload_result_notes"] + len(ids)
                or after["upload_observations"] != before["upload_observations"] - len(ids)):
            print(f"WARNING: retyped {len(ids)}, planned {len(plan.targets)}; after {after}",
                  file=sys.stderr)
            sys.exit(2)
        print(f"\nApplied. {len(ids)} notes retyped to result_note (matches the dry-run plan).")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry run)")
    args = parser.parse_args()
    main(apply=args.apply)
