"""One-time cleanup: collapse duplicate experimental_conditions rows, then
backfill every stale denormalized experiment_id string from its experiment_fk.

Background
----------
experimental_conditions carries two identities: experiment_fk (authoritative,
non-null FK) and a denormalized experiment_id string that, until 2026-08-05, no
rename path updated -- both paths now sync it via
backend/services/denormalized_ids.py, so nothing new accumulates behind this
cleanup (see the issue doc's Follow-up). As of the 2026-08-05 production dump,
187 of 1013 rows (18%) carry a string that is not their experiment's ID --
almost all of it rename debris from the replicate/-t<days> ID migration (e.g.
cond 901 still says 'SERUM_cation_031' for the experiment now called
'SERUM_Cation_011a-t5').

That mismatch is what produced the duplicate. GET /api/conditions/by-experiment
resolved conditions by the STRING, so it 404'd for 175 experiments that do have
a conditions row; the detail page then offered "Add Details", and POST
/api/conditions inserted a second row with no existence check. Exactly one
experiment reached that state: SERUM_Cation_011a-t5, cond 901 + cond 1062,
value-identical, each with its own copy of the same Mg(OH)2 0.149 g additive.

Downstream, a duplicate 500s the experiments list (_build_list_item), fans out
the list join, duplicates the Power BI dimension key in v_experiments, and
blocks deletion (serialize_experiment_snapshot).

Order matters
-------------
Dedupe runs BEFORE backfill. Backfilling first would set both rows of a
duplicate pair to the same string, and the 6 strings that already appear on two
rows would multiply. --apply runs both in that order.

Selection is by rule, not by hardcoded id
-----------------------------------------
Survivor: the row whose experiment_id already equals its experiment's real ID;
if none (or several) qualify, the lowest id. A duplicate is deleted only when it
is EQUIVALENT to the survivor -- every measurement column equal, and no additive
that the survivor does not also have (ChemicalAdditive.experiment_id is an
integer FK to experimental_conditions.id, and the relationship is
delete-orphan, so deleting a row destroys its additives). Anything else is
reported and left alone for a human.

reactor_slot is NOT affected
----------------------------
Per MODELS.md's bulk-update caveat, a Core/bulk UPDATE does not fire the
set_reactor_slot mapper listener. This script's backfill touches only
experiment_id, and reactor_slot derives from (reactor_number, experiment_type),
so no recompute is needed. The dedupe path deletes through the ORM.

See docs/issues/issue-duplicate-conditions-rows-and-stale-experiment-id-strings.md

Usage:
    # Dry run (preview only, no writes)
    python database/data_migrations/dedupe_conditions_and_backfill_ids_018.py

    # Apply
    python database/data_migrations/dedupe_conditions_and_backfill_ids_018.py --apply
"""
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from database import get_db  # noqa: E402
from database.models.chemicals import ChemicalAdditive  # noqa: E402
from database.models.conditions import ExperimentalConditions  # noqa: E402
from database.models.experiments import Experiment  # noqa: E402

# Identity, audit and derived columns are never compared -- they are expected to
# differ between a row created with the experiment and one added later.
_IGNORED_COLUMNS = {
    "id", "experiment_id", "experiment_fk", "created_at", "updated_at",
    "water_to_rock_ratio", "total_ferrous_iron_g", "catalyst_percentage",
    "catalyst_ppm", "reactor_slot",
}


@dataclass
class DuplicateGroup:
    experiment_fk: int
    experiment_id: str
    keep_id: int
    delete_ids: list[int] = field(default_factory=list)
    blocked_reason: str | None = None


@dataclass
class StaleString:
    conditions_id: int
    current: str
    correct: str


def _comparable_columns() -> list[str]:
    return [c.name for c in ExperimentalConditions.__table__.columns
            if c.name not in _IGNORED_COLUMNS]


def _additive_key(additive: ChemicalAdditive) -> tuple:
    return (additive.compound_id, additive.amount, additive.unit)


def _additive_keys(db: Session, conditions_id: int) -> list[tuple]:
    rows = db.execute(
        select(ChemicalAdditive).where(ChemicalAdditive.experiment_id == conditions_id)
    ).scalars().all()
    return sorted(_additive_key(a) for a in rows)


def find_duplicate_groups(db: Session) -> list[DuplicateGroup]:
    """One entry per experiment holding more than one conditions row."""
    fks = db.execute(text("""
        SELECT experiment_fk FROM experimental_conditions
        GROUP BY experiment_fk HAVING COUNT(*) > 1 ORDER BY experiment_fk
    """)).scalars().all()

    groups: list[DuplicateGroup] = []
    for fk in fks:
        exp = db.get(Experiment, fk)
        real_id = exp.experiment_id if exp else ""
        rows = db.execute(
            select(ExperimentalConditions)
            .where(ExperimentalConditions.experiment_fk == fk)
            .order_by(ExperimentalConditions.id)
        ).scalars().all()

        correct = [r for r in rows if r.experiment_id == real_id]
        keep = correct[0] if len(correct) == 1 else rows[0]
        doomed = [r for r in rows if r.id != keep.id]

        reasons: list[str] = []
        keep_additives = _additive_keys(db, keep.id)
        for row in doomed:
            for column in _comparable_columns():
                if getattr(row, column) != getattr(keep, column):
                    reasons.append(
                        f"cond {row.id} differs from survivor {keep.id} on "
                        f"{column} ({getattr(row, column)!r} vs "
                        f"{getattr(keep, column)!r})"
                    )
            for key in _additive_keys(db, row.id):
                if key not in keep_additives:
                    reasons.append(
                        f"cond {row.id} holds an additive the survivor {keep.id} "
                        f"does not: compound_id={key[0]} amount={key[1]} unit={key[2]}"
                    )

        groups.append(DuplicateGroup(
            experiment_fk=fk,
            experiment_id=real_id,
            keep_id=keep.id,
            delete_ids=[r.id for r in doomed],
            blocked_reason="; ".join(reasons) or None,
        ))
    return groups


def find_stale_strings(db: Session) -> list[StaleString]:
    """Conditions rows whose denormalized string is not their FK's real ID."""
    rows = db.execute(text("""
        SELECT ec.id, ec.experiment_id AS current, e.experiment_id AS correct
        FROM experimental_conditions ec
        JOIN experiments e ON e.id = ec.experiment_fk
        WHERE ec.experiment_id IS DISTINCT FROM e.experiment_id
        ORDER BY ec.id
    """)).mappings().all()
    return [StaleString(r["id"], r["current"], r["correct"]) for r in rows]


def dedupe(db: Session, groups: list[DuplicateGroup]) -> tuple[list[int], list[str]]:
    """Delete equivalent duplicates through the ORM. Flushes; does not commit."""
    deleted: list[int] = []
    refusals: list[str] = []
    for group in groups:
        if group.blocked_reason:
            refusals.append(
                f"{group.experiment_id} (experiment_fk={group.experiment_fk}): "
                f"{group.blocked_reason}"
            )
            continue
        for cond_id in group.delete_ids:
            row = db.get(ExperimentalConditions, cond_id)
            if row is not None:
                db.delete(row)  # delete-orphan removes its additives
                deleted.append(cond_id)
    db.flush()
    return deleted, refusals


def backfill_strings(db: Session) -> int:
    """Set every conditions.experiment_id to its FK's real ID. Flushes."""
    result = db.execute(text("""
        UPDATE experimental_conditions AS ec
        SET experiment_id = e.experiment_id
        FROM experiments AS e
        WHERE e.id = ec.experiment_fk
          AND ec.experiment_id IS DISTINCT FROM e.experiment_id
    """))
    db.flush()
    return result.rowcount or 0


def main(apply: bool) -> None:
    db = next(get_db())
    try:
        groups = find_duplicate_groups(db)
        stale = find_stale_strings(db)

        print(f"Experiments with duplicate conditions rows: {len(groups)}")
        for group in groups:
            verdict = "BLOCKED" if group.blocked_reason else "deletable"
            print(f"  {group.experiment_id} (experiment_fk={group.experiment_fk}): "
                  f"keep {group.keep_id}, delete {group.delete_ids} [{verdict}]")
            if group.blocked_reason:
                print(f"      {group.blocked_reason}")

        print(f"\nConditions rows with a stale experiment_id string: {len(stale)}")
        for row in stale[:20]:
            print(f"  cond {row.conditions_id}: {row.current!r} -> {row.correct!r}")
        if len(stale) > 20:
            print(f"  ... and {len(stale) - 20} more")

        if not apply:
            print("\nDry run -- pass --apply to commit changes.")
            return

        deleted, refusals = dedupe(db, groups)
        updated = backfill_strings(db)
        db.commit()

        print(f"\nDeleted {len(deleted)} duplicate conditions row(s): {deleted}")
        print(f"Backfilled {updated} experiment_id string(s).")
        if refusals:
            print(f"\nREFUSED {len(refusals)} group(s) -- resolve by hand:")
            for line in refusals:
                print(f"  {line}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the changes")
    main(parser.parse_args().apply)
