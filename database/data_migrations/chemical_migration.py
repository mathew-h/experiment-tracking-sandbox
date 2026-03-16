from database import SessionLocal
from database.models import ExperimentalConditions, ChemicalAdditive, Compound, AmountUnit
from sqlalchemy import func


def _get_or_create_compound(db, name: str) -> tuple[Compound, bool]:
    """Return (Compound, created_flag) by name (case-insensitive); create if missing."""
    if not name or not name.strip():
        return None, False
    existing = (
        db.query(Compound)
        .filter(func.lower(Compound.name) == name.strip().lower())
        .first()
    )
    if existing:
        return existing, False
    comp = Compound(name=name.strip(), notes="Created by chemical migration")
    db.add(comp)
    db.flush()
    return comp, True


def _upsert_additive(
    db,
    conditions_id: int,
    compound_id: int,
    amount: float,
    unit: AmountUnit,
    order_val: int = None,
    method: str = None,
):
    """Create or update ChemicalAdditive for (conditions, compound)."""
    if amount is None:
        return False
    existing = (
        db.query(ChemicalAdditive)
        .filter(
            ChemicalAdditive.experiment_id == conditions_id,
            ChemicalAdditive.compound_id == compound_id,
        )
        .first()
    )
    if existing:
        existing.amount = amount
        existing.unit = unit
        existing.addition_order = order_val
        existing.addition_method = method
        existing.calculate_derived_values()
        return False  # updated
    add = ChemicalAdditive(
        experiment_id=conditions_id,
        compound_id=compound_id,
        amount=amount,
        unit=unit,
        addition_order=order_val,
        addition_method=method,
    )
    add.calculate_derived_values()
    db.add(add)
    return True  # created


def migrate_conditions_to_additives(
    *,
    dry_run: bool = False,
    create_missing_compounds: bool = True,
) -> dict:
    """
    Migrate selected fields from ExperimentalConditions into ChemicalAdditive records.

    Rules implemented:
    - catalyst + catalyst_mass -> Compound(name=catalyst), amount in grams, unit=GRAM
    - surfactant_type + surfactant_concentration -> Compound(name=surfactant_type), amount in mM, unit=MILLIMOLAR
    - buffer_system + buffer_concentration -> Compound(name=buffer_system), amount in M, unit=MOLAR

    Returns a summary dict with counts.
    """
    db = SessionLocal()
    summary = {
        "conditions_scanned": 0,
        "compounds_created": 0,
        "additives_created": 0,
        "additives_updated": 0,
        "errors": 0,
    }
    try:
        conditions_list = db.query(ExperimentalConditions).all()
        for cond in conditions_list:
            summary["conditions_scanned"] += 1
            try:
                # Catalyst -> grams
                if cond.catalyst and cond.catalyst_mass is not None and cond.catalyst_mass > 0:
                    comp = None
                    if create_missing_compounds:
                        comp, was_created = _get_or_create_compound(db, cond.catalyst)
                        if was_created:
                            summary["compounds_created"] += 1
                    else:
                        comp = (
                            db.query(Compound)
                            .filter(func.lower(Compound.name) == cond.catalyst.strip().lower())
                            .first()
                        )
                    if comp:
                        created = _upsert_additive(
                            db,
                            conditions_id=cond.id,
                            compound_id=comp.id,
                            amount=float(cond.catalyst_mass),
                            unit=AmountUnit.GRAM,
                            order_val=1,
                            method="migration",
                        )
                        if created:
                            summary["additives_created"] += 1
                        else:
                            summary["additives_updated"] += 1

                # Surfactant -> mM
                if cond.surfactant_type and cond.surfactant_concentration is not None and cond.surfactant_concentration > 0:
                    comp = None
                    if create_missing_compounds:
                        comp, was_created = _get_or_create_compound(db, cond.surfactant_type)
                        if was_created:
                            summary["compounds_created"] += 1
                    else:
                        comp = (
                            db.query(Compound)
                            .filter(func.lower(Compound.name) == cond.surfactant_type.strip().lower())
                            .first()
                        )
                    if comp:
                        created = _upsert_additive(
                            db,
                            conditions_id=cond.id,
                            compound_id=comp.id,
                            amount=float(cond.surfactant_concentration),
                            unit=AmountUnit.MILLIMOLAR,
                            order_val=2,
                            method="migration",
                        )
                        if created:
                            summary["additives_created"] += 1
                        else:
                            summary["additives_updated"] += 1

                # Buffer -> mM (optional; buffer_concentration documented as mM)
                if cond.buffer_system and cond.buffer_concentration is not None and cond.buffer_concentration > 0:
                    comp = None
                    if create_missing_compounds:
                        comp, was_created = _get_or_create_compound(db, cond.buffer_system)
                        if was_created:
                            summary["compounds_created"] += 1
                    else:
                        comp = (
                            db.query(Compound)
                            .filter(func.lower(Compound.name) == cond.buffer_system.strip().lower())
                            .first()
                        )
                    if comp:
                        created = _upsert_additive(
                            db,
                            conditions_id=cond.id,
                            compound_id=comp.id,
                            amount=float(cond.buffer_concentration),
                            unit=AmountUnit.MILLIMOLAR,
                            order_val=3,
                            method="migration",
                        )
                        if created:
                            summary["additives_created"] += 1
                        else:
                            summary["additives_updated"] += 1

                # Ammonium chloride (deprecated) -> mM
                if (
                    hasattr(cond, "ammonium_chloride_concentration")
                    and cond.ammonium_chloride_concentration is not None
                    and cond.ammonium_chloride_concentration > 0
                ):
                    comp = None
                    if create_missing_compounds:
                        comp, was_created = _get_or_create_compound(db, "Ammonium Chloride")
                        if was_created:
                            summary["compounds_created"] += 1
                    else:
                        comp = (
                            db.query(Compound)
                            .filter(func.lower(Compound.name) == "ammonium chloride")
                            .first()
                        )
                    if comp:
                        created = _upsert_additive(
                            db,
                            conditions_id=cond.id,
                            compound_id=comp.id,
                            amount=float(cond.ammonium_chloride_concentration),
                            unit=AmountUnit.MILLIMOLAR,
                            order_val=4,
                            method="migration",
                        )
                        if created:
                            summary["additives_created"] += 1
                        else:
                            summary["additives_updated"] += 1

            except Exception:
                summary["errors"] += 1

        if dry_run:
            db.rollback()
        else:
            db.commit()
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    # Simple manual runner for local use
    result = migrate_conditions_to_additives(dry_run=False, create_missing_compounds=True)
    print(result)


def run_migration():
    """Entry point for scripts/run_data_migration.py runner."""
    summary = migrate_conditions_to_additives(dry_run=False, create_missing_compounds=True)
    print(summary)
    return True


