"""Writes to an experiment's chemical additives (issue #190, D-07).

The one place a ChemicalAdditive row is created, changed or deleted from the
API. Every write here does three things the routers used to repeat:

1. flushes the row, then calls ``recalculate(additive, db)`` explicitly. That
   call is what produces the stored derived fields (mass_in_grams, moles_added,
   final_concentration, elemental_metal_mass, catalyst_percentage,
   catalyst_ppm). The mapper listener in database/event_listeners.py runs
   earlier, before the relationships it reads are loaded, so it must not be
   relied on;
2. writes a ModificationsLog row, signed with the user's **email**
   (decision H-05, 2026-11-13; rows written earlier may carry a Firebase uid);
3. leaves the commit to the caller.

New code that writes an additive must go through this module. See
docs/working/decisions.md (2026-11-13). The bulk-upload parsers have their own
write path and are out of scope here.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

import backend.services.calculations  # noqa: F401 — registers @register decorators
from backend.services.audit import audit_values
from backend.services.calculations.registry import recalculate
from database.models.chemicals import ChemicalAdditive, Compound
from database.models.conditions import ExperimentalConditions
from database.models.experiments import Experiment, ModificationsLog

_TABLE = "chemical_additives"


def owning_experiment(db: Session, additive: ChemicalAdditive) -> Optional[Experiment]:
    """The experiment an additive belongs to, or None if its conditions row is gone.

    ChemicalAdditive.experiment_id is a foreign key to experimental_conditions.id,
    not to experiments.id.
    """
    conditions = db.get(ExperimentalConditions, additive.experiment_id)
    return db.get(Experiment, conditions.experiment_fk) if conditions else None


def find_additive(db: Session, conditions_id: int, compound_id: int) -> Optional[ChemicalAdditive]:
    """The additive for this compound on this conditions row, or None."""
    return db.execute(
        select(ChemicalAdditive)
        .where(ChemicalAdditive.experiment_id == conditions_id)
        .where(ChemicalAdditive.compound_id == compound_id)
    ).scalar_one_or_none()


def _amount_and_unit(additive: ChemicalAdditive) -> dict[str, Any]:
    return {"amount": additive.amount, "unit": additive.unit.value if additive.unit else None}


def _log(
    db: Session, exp: Experiment, user_email: str, modification_type: str,
    old_values: Optional[dict], new_values: Optional[dict],
) -> None:
    db.add(ModificationsLog(
        experiment_id=exp.experiment_id,
        experiment_fk=exp.id,
        modified_by=user_email,
        modification_type=modification_type,
        modified_table=_TABLE,
        old_values=old_values,
        new_values=new_values,
    ))


def upsert_additive(
    db: Session, exp: Experiment, conditions: ExperimentalConditions, compound_id: int,
    fields: dict[str, Any], fields_set: dict[str, Any], user_email: str,
) -> ChemicalAdditive:
    """Create the additive for ``compound_id``, or update the one already there.

    ``fields`` is the full payload (used to create); ``fields_set`` is only what
    the caller sent (used to update, so an omitted field is left alone). The
    audit row records amount and unit, before and after.
    """
    additive = find_additive(db, conditions.id, compound_id)
    if additive is not None:
        old_values: Optional[dict] = _amount_and_unit(additive)
        modification_type = "update"
        for key, value in fields_set.items():
            setattr(additive, key, value)
    else:
        old_values = None
        modification_type = "create"
        additive = ChemicalAdditive(experiment_id=conditions.id, compound_id=compound_id, **fields)
        db.add(additive)
    db.flush()
    recalculate(additive, db)
    _log(db, exp, user_email, modification_type, old_values, _amount_and_unit(additive))
    return additive


def patch_additive(
    db: Session, additive: ChemicalAdditive, fields_set: dict[str, Any], user_email: str,
) -> ChemicalAdditive:
    """Apply a partial update. The audit row records each changed field.

    The flush can raise IntegrityError when ``compound_id`` changes to one the
    experiment already has; the caller turns that into its 409.
    """
    old_values = audit_values({key: getattr(additive, key) for key in fields_set})
    for key, value in fields_set.items():
        setattr(additive, key, value)
    db.flush()
    recalculate(additive, db)
    exp = owning_experiment(db, additive)
    if exp is not None:
        _log(db, exp, user_email, "update", old_values, audit_values(fields_set))
    return additive


def delete_additive(
    db: Session, additive: ChemicalAdditive, exp: Optional[Experiment], user_email: str,
) -> None:
    """Delete an additive and record what it held. No audit row if ``exp`` is None."""
    compound = db.get(Compound, additive.compound_id)
    old_values = {
        "compound_id": additive.compound_id,
        "compound_name": compound.name if compound else None,
        **_amount_and_unit(additive),
    }
    db.delete(additive)
    if exp is not None:
        _log(db, exp, user_email, "delete", old_values, None)
