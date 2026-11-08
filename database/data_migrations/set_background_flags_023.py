"""One-time backfill: set experiments.is_background on a confirmed list (issue #152).

Background
----------
Issue #152 added experiments.is_background (default false). Which existing
experiments are backgrounds is a question for the experimenters, answered from
the #151 report (docs/issues/issue-151-serum-zero-rock-mass-report.md). This
script applies their confirmed answer; it decides nothing itself.

Input
-----
A text or CSV file of experiment IDs to flag, one per line. Blank lines and
lines starting with '#' are ignored. A CSV with a header row is read from its
`experiment_id` column (other columns are ignored), so the report's tables can
be pasted into a sheet and saved as CSV.

Rules
-----
* Only sets is_background = true. Never clears a flag (use the UI for that).
* An ID already flagged is reported as unchanged and gets no audit row.
* An unknown ID is reported and skipped; it never stops the run.
* Each change writes ModificationsLog(modification_type='update',
  modified_table='experiments', modified_by='set_background_flags_023',
  old_values={'is_background': false}, new_values={'is_background': true}),
  the same shape as PATCH /api/experiments/{id}.
* One transaction, one commit, in main(). Idempotent: a second --apply
  changes nothing.

Usage
-----
    # Dry run (default): prints the plan, writes nothing
    PYTHONPATH=. python database/data_migrations/set_background_flags_023.py backgrounds.csv

    # Apply, only after the dry run has been checked
    PYTHONPATH=. python database/data_migrations/set_background_flags_023.py backgrounds.csv --apply
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from database import get_db  # noqa: E402
from database.models.experiments import Experiment, ModificationsLog  # noqa: E402

SOURCE_TAG = "set_background_flags_023"


@dataclass
class Plan:
    to_flag: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


def read_ids(path: Path) -> list[str]:
    """IDs from a one-per-line file or a CSV with an experiment_id column, in
    file order, duplicates dropped."""
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    first = next((ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")), "")
    if "experiment_id" in [c.strip().lower() for c in first.split(",")]:
        rows = csv.DictReader(ln for ln in lines if not ln.lstrip().startswith("#"))
        key = next(k for k in rows.fieldnames or [] if k.strip().lower() == "experiment_id")
        raw = [(row.get(key) or "") for row in rows]
    else:
        raw = [ln.split(",")[0] for ln in lines if not ln.lstrip().startswith("#")]
    seen: dict[str, None] = {}
    for value in raw:
        value = value.strip()
        if value:
            seen.setdefault(value, None)
    return list(seen)


def build_plan(db: Session, ids: list[str]) -> Plan:
    found = {
        exp.experiment_id: exp
        for exp in db.execute(select(Experiment).where(Experiment.experiment_id.in_(ids))).scalars()
    }
    plan = Plan()
    for exp_id in ids:
        exp = found.get(exp_id)
        if exp is None:
            plan.unknown.append(exp_id)
        elif exp.is_background:
            plan.already.append(exp_id)
        else:
            plan.to_flag.append(exp_id)
    return plan


def apply_plan(db: Session, plan: Plan) -> int:
    exps = db.execute(
        select(Experiment).where(Experiment.experiment_id.in_(plan.to_flag))
    ).scalars().all()
    for exp in exps:
        db.add(ModificationsLog(
            experiment_id=exp.experiment_id,
            experiment_fk=exp.id,
            modified_by=SOURCE_TAG,
            modification_type="update",
            modified_table="experiments",
            old_values={"is_background": False},
            new_values={"is_background": True},
        ))
        exp.is_background = True
    db.flush()
    return len(exps)


def print_report(plan: Plan) -> None:
    print(f"to flag:   {len(plan.to_flag)}")
    print(f"unchanged: {len(plan.already)} (already backgrounds)")
    print(f"unknown:   {len(plan.unknown)}")
    for label, ids in (("TO FLAG", plan.to_flag), ("UNKNOWN (skipped)", plan.unknown)):
        if ids:
            print(f"\n{label}:")
            for exp_id in ids:
                print(f"  {exp_id}")


def main(path: Path, apply: bool) -> None:
    ids = read_ids(path)
    print(f"{len(ids)} IDs read from {path}")
    db = next(get_db())
    try:
        plan = build_plan(db, ids)
        print_report(plan)
        if not apply:
            print("\nDry run — pass --apply to commit changes.")
            return
        n = apply_plan(db, plan)
        db.commit()
        if n != len(plan.to_flag):
            print(f"WARNING: flagged {n}, planned {len(plan.to_flag)}", file=sys.stderr)
            sys.exit(2)
        print(f"\nApplied. {n} experiments flagged as backgrounds (matches the dry-run plan).")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ids_file", type=Path, help="Experiment IDs to flag (one per line, or CSV with experiment_id)")
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry run)")
    args = parser.parse_args()
    main(args.ids_file, apply=args.apply)
