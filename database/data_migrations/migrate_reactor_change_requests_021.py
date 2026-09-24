"""One-time backfill: convert reactor_change_requests rows into dated
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
5. Idempotent. A row is ALREADY CONVERTED when a note exists with the same
   experiment_fk, event_date, note_text and created_by=SOURCE_TAG. Two source
   rows sharing (experiment, date, text) -- possible only under two different
   reactor_labels, because of the table's unique key -- COLLAPSE into one
   note; the second is reported as collapsed, never doubled or dropped silently.
6. Informational: how many convertible rows carry a reactor_label that differs
   from the experiment's current experimental_conditions.reactor_slot. A
   difference is expected when an experiment moved reactors; it is reported so
   Mat can judge whether the label must be kept (decision 2's open question).

Usage
-----
    # Dry run (default): prints the report, writes nothing
    PYTHONPATH=. python database/data_migrations/migrate_reactor_change_requests_021.py

    # Apply -- ONLY after Mat has audited the dry-run report
    PYTHONPATH=. python database/data_migrations/migrate_reactor_change_requests_021.py --apply

    # Against a specific database (defaults to $DATABASE_URL, then the dev DB)
    DATABASE_URL=postgresql://... python database/data_migrations/migrate_reactor_change_requests_021.py
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.services.notes import add_note
from database import get_db  # noqa: E402
from database.models.conditions import ExperimentalConditions
from database.models.enums import NoteType
from database.models.experiments import Experiment, ExperimentNotes, ModificationsLog
from database.models.notion_sync import ReactorChangeRequest

SOURCE_TAG = "migrate_change_requests_021"
SAMPLE_SIZE = 20


@dataclass
class Plan:
    total: int = 0
    convertible: list[ReactorChangeRequest] = field(default_factory=list)
    orphaned: list[ReactorChangeRequest] = field(default_factory=list)      # experiment_id IS NULL
    blank: list[ReactorChangeRequest] = field(default_factory=list)
    already_converted: list[ReactorChangeRequest] = field(default_factory=list)
    collapsed: list[ReactorChangeRequest] = field(default_factory=list)     # same (exp, date, text) as an earlier row
    label_disagreements: int = 0
    dashboard_typed: int = 0      # notion_page_id IS NULL
    notion_imported: int = 0      # notion_page_id IS NOT NULL
    experiments: dict[str, Experiment] = field(default_factory=dict)        # experiment_id -> row (resolved)


def _row_dict(row: ReactorChangeRequest) -> dict:
    """The full original row, JSON-safe, for the ModificationsLog snapshot."""
    def iso(v):
        return v.isoformat() if isinstance(v, (date, datetime)) else v
    return {
        "id": row.id,
        "reactor_label": row.reactor_label,
        "experiment_id": row.experiment_id,
        "requested_change": row.requested_change,
        "notion_status": row.notion_status,
        "carried_forward": row.carried_forward,
        "sync_date": iso(row.sync_date),
        "notion_page_id": row.notion_page_id,
        "created_at": iso(row.created_at),
    }


def build_plan(db: Session) -> Plan:
    """Read-only. Everything --apply will do is decided here."""
    plan = Plan()
    rows = db.execute(select(ReactorChangeRequest).order_by(ReactorChangeRequest.id)).scalars().all()
    plan.total = len(rows)

    exp_ids = sorted({r.experiment_id for r in rows if r.experiment_id is not None})
    if exp_ids:
        for exp in db.execute(select(Experiment).where(Experiment.experiment_id.in_(exp_ids))).scalars():
            plan.experiments[exp.experiment_id] = exp
    slots: dict[int, Optional[str]] = {}
    if plan.experiments:
        fks = [e.id for e in plan.experiments.values()]
        for fk, slot in db.execute(
            select(ExperimentalConditions.experiment_fk, ExperimentalConditions.reactor_slot)
            .where(ExperimentalConditions.experiment_fk.in_(fks))
        ).all():
            slots[fk] = slot

    existing = {
        (n.experiment_fk, n.event_date, n.note_text)
        for n in db.execute(
            select(ExperimentNotes.experiment_fk, ExperimentNotes.event_date, ExperimentNotes.note_text)
            .where(ExperimentNotes.created_by == SOURCE_TAG, ExperimentNotes.note_type == NoteType.modification)
        ).all()
    }
    seen_this_run: set[tuple[int, date, str]] = set()

    for row in rows:
        if row.notion_page_id is None:
            plan.dashboard_typed += 1
        else:
            plan.notion_imported += 1
        if row.experiment_id is None:
            plan.orphaned.append(row)
            continue
        exp = plan.experiments.get(row.experiment_id)
        if exp is None:
            # Cannot happen while the FK holds; reported rather than raised so a
            # dry run against a DB with the FK dropped still produces a report.
            plan.orphaned.append(row)
            continue
        text_ = (row.requested_change or "").strip()
        if not text_:
            plan.blank.append(row)
            continue
        key = (exp.id, row.sync_date, text_)
        if key in existing:
            plan.already_converted.append(row)
            continue
        if key in seen_this_run:
            plan.collapsed.append(row)
            continue
        seen_this_run.add(key)
        plan.convertible.append(row)
        if slots.get(exp.id) != row.reactor_label:
            plan.label_disagreements += 1
    return plan


def _sample(items, n=SAMPLE_SIZE):
    return items[:n]


def _short(text_: Optional[str], width: int = 60) -> str:
    t = (text_ or "").replace("\n", " ")
    return t if len(t) <= width else t[: width - 1] + "…"


def print_report(plan: Plan) -> None:
    p = print
    p("== migrate_reactor_change_requests_021 -- dry-run report ==")
    p(f"reactor_change_requests rows:                    {plan.total}")
    p(f"  typed on the dashboard (notion_page_id NULL):  {plan.dashboard_typed}")
    p(f"  imported from Notion:                          {plan.notion_imported}")
    p(f"convertible (-> one 'modification' note each):   {len(plan.convertible)}")
    p(f"orphaned (experiment_id NULL; FK ON DELETE SET NULL): {len(plan.orphaned)}")
    for r in plan.orphaned:
        p(f"    row {r.id}: {r.reactor_label} {r.sync_date} {'notion' if r.notion_page_id else 'dashboard'} "
          f"'{_short(r.requested_change)}'")
    p(f"blank requested_change:                          {len(plan.blank)}")
    for r in plan.blank:
        p(f"    row {r.id}: {r.reactor_label} {r.sync_date} exp={r.experiment_id}")
    p(f"already converted by a prior run (skipped):      {len(plan.already_converted)}")
    p(f"collapsed under (experiment, date, text):        {len(plan.collapsed)}")
    for r in plan.collapsed:
        p(f"    row {r.id}: {r.reactor_label} {r.sync_date} exp={r.experiment_id} '{_short(r.requested_change)}'")
    p(f"reactor_label != current conditions.reactor_slot: {plan.label_disagreements} of {len(plan.convertible)} (informational)")
    p(f"-- sample of {min(SAMPLE_SIZE, len(plan.convertible))} convertible rows --")
    for r in _sample(plan.convertible):
        p(f"    row {r.id}: {r.reactor_label} {r.sync_date} exp={r.experiment_id} "
          f"{'notion' if r.notion_page_id else 'dashboard'} '{_short(r.requested_change)}'")


def apply_plan(db: Session, plan: Plan) -> list[int]:
    """Convert every plan.convertible row; return the new note ids in order."""
    note_ids: list[int] = []
    for row in plan.convertible:
        exp = plan.experiments[row.experiment_id]
        note = add_note(
            db,
            exp,
            (row.requested_change or "").strip(),
            note_type=NoteType.modification,
            event_date=row.sync_date,
            created_by=SOURCE_TAG,
            created_at=row.created_at,
        )
        db.add(ModificationsLog(
            experiment_id=exp.experiment_id,
            experiment_fk=exp.id,
            modified_by=SOURCE_TAG,
            modification_type="update",
            modified_table="reactor_change_requests",
            old_values=_row_dict(row),
            new_values={"note_id": note.id},
        ))
        note_ids.append(note.id)
    db.flush()
    return note_ids


def after_counts(db: Session) -> dict:
    def q(sql: str) -> int:
        from sqlalchemy import text
        return db.execute(text(sql)).scalar_one()
    return {
        "change_request_rows": q("SELECT COUNT(*) FROM reactor_change_requests"),
        "modification_notes": q("SELECT COUNT(*) FROM experiment_notes WHERE note_type = 'modification'"),
        "dated_modification_notes": q("SELECT COUNT(*) FROM experiment_notes WHERE note_type = 'modification' AND event_date IS NOT NULL"),
        "notes_by_021": q(f"SELECT COUNT(*) FROM experiment_notes WHERE created_by = '{SOURCE_TAG}'"),
        "snapshots_by_021": q("SELECT COUNT(*) FROM modifications_log WHERE modified_table = 'reactor_change_requests'"),
        "notes_total": q("SELECT COUNT(*) FROM experiment_notes"),
    }


def main(apply: bool) -> None:
    db = next(get_db())
    try:
        before = after_counts(db)
        plan = build_plan(db)
        print_report(plan)
        print("before:", before)
        if not apply:
            print("\nDry run — pass --apply to commit changes.")
            return
        ids = apply_plan(db, plan)
        db.commit()
        after = after_counts(db)
        print("after: ", after)
        expected = before["notes_by_021"] + len(plan.convertible)
        if after["notes_by_021"] != expected or len(ids) != len(plan.convertible):
            print(f"WARNING: converted {len(ids)}, expected {len(plan.convertible)}; "
                  f"notes_by_021 {after['notes_by_021']} vs expected {expected}", file=sys.stderr)
            sys.exit(2)
        print(f"\nApplied. {len(ids)} notes created (matches the dry-run plan).")
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
