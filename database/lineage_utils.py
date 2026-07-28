from __future__ import annotations

"""
Utility functions for managing experiment lineage.

This module provides functions to parse experiment IDs, identify derivations,
and establish parent-child relationships between experiments.

Supports hybrid delimiter system:
- Hyphen-NUMBER for sequential lineage (e.g., -2, -3)
- Underscore-TEXT for treatment variants (e.g., _Desorption)

The experiment ID grammar itself now lives in database/experiment_id_parser.py
(issue #70 P5 consolidation); parse_experiment_id below delegates to it.
"""
import logging
from typing import Optional, Tuple, TYPE_CHECKING
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from .experiment_id_parser import parse_lineage_fields, split_timepoint_token

if TYPE_CHECKING:
    from .models import Experiment

logger = logging.getLogger(__name__)


def _reject_self_parent(experiment, parent):
    """Guard against an experiment being resolved as its own lineage parent.

    A self-referential value on the ``parent_experiment_fk`` FK is never a valid
    lineage result and makes SQLAlchemy raise ``CircularDependencyError`` at flush
    (issue #86: a loose normalize match can resolve a renamed row against itself
    before its rename is flushed). Returns ``None`` when ``parent`` is the
    experiment itself — by identity or by matching primary key — otherwise returns
    ``parent`` unchanged. Emits a warning-level log when it drops a self-parent so
    a future collision is visible rather than silent.
    """
    if parent is None:
        return None
    if parent is experiment or (
        parent.id is not None
        and experiment.id is not None
        and parent.id == experiment.id
    ):
        logger.warning(
            "Dropping self-referential lineage parent for experiment_id=%r "
            "(resolved parent is the experiment itself)",
            experiment.experiment_id,
        )
        return None
    return parent


def parse_experiment_id(experiment_id: str) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]:
    """
    Parse an experiment ID into (base_experiment_id, derivation_number,
    treatment_variant, replicate_label).

    Delegates to the canonical grammar in database/experiment_id_parser.py
    (issue #70 P5 consolidation) — see parse_lineage_fields there for the
    full delimiter rules and examples. Kept as a public wrapper because it
    is the 4-tuple surface used throughout lineage handling, event
    listeners, replicate routing, tests, and the data-migration script.
    """
    return parse_lineage_fields(experiment_id)


def _normalize_experiment_id(value: str) -> str:
    """Lowercase and strip hyphens/underscores/spaces for loose experiment_id matching."""
    return ''.join(ch for ch in value.lower() if ch not in ['-', '_', ' '])


def _find_experiment_by_exact_spelling(db: Session, candidate_id: str):
    """
    Resolve a single experiment_id spelling to its Experiment row.

    Checks the session's pending, not-yet-flushed new objects first. This matters
    because callers of this helper (find_replicate_group_parent, and in turn
    update_orphaned_derivations) run from the `before_flush` event listener: at that
    point in the flush lifecycle, a brand-new group-parent row being inserted in the
    SAME flush has no primary key yet and is invisible to a plain `db.query(...)`
    SELECT (autoflush is off, and the INSERT hasn't executed yet). Without this check,
    creating a group parent for pre-existing orphaned replicates would silently fail
    to back-link them, because the parent could never resolve to itself mid-flush.
    Falls back to a normal DB query for already-persisted rows (the common case).
    """
    from .models import Experiment

    candidate_norm = _normalize_experiment_id(candidate_id)

    for obj in db.new:
        if (
            isinstance(obj, Experiment)
            and obj.experiment_id
            and _normalize_experiment_id(obj.experiment_id) == candidate_norm
        ):
            return obj

    return db.query(Experiment).filter(
        func.lower(
            func.replace(
                func.replace(
                    func.replace(Experiment.experiment_id, '-', ''),
                    '_', ''
                ),
                ' ', ''
            )
        ) == candidate_norm
    ).first()


def find_replicate_group_parent(db: Session, base_id: str):
    """
    Resolve the group parent for a replicate member, in precedence order:
    bare stem (S), then the explicit parent spellings S-0 and S-1.

    Args:
        db: Database session
        base_id: The stem (e.g. "SERUM_001") to resolve a parent for

    Returns:
        The parent Experiment object if found, None otherwise
    """
    if not base_id:
        return None

    for candidate_id in (base_id, f"{base_id}-0", f"{base_id}-1"):
        parent = _find_experiment_by_exact_spelling(db, candidate_id)
        if parent:
            return parent
    return None


def get_or_find_parent_experiment(db: Session, experiment_id: str):
    """
    Find the parent experiment for a given experiment ID.
    
    For sequential experiments (e.g., EXP-001-4):
    - Finds highest sequential number less than current (EXP-001-3, or EXP-001-2, or EXP-001)
    - Supports skipped sequential numbers
    
    For treatment experiments (e.g., EXP-001_Desorption or EXP-001-2_Desorption):
    - Finds the base experiment (with or without sequential number)
    
    Args:
        db: Database session
        experiment_id: The experiment ID to find the parent for
        
    Returns:
        The parent Experiment object if found, None otherwise
        
    Note:
        This function will import Experiment model inside to avoid circular imports.
    """
    from .models import Experiment
    
    base_id, derivation_num, treatment_variant, _replicate_label = parse_experiment_id(experiment_id)

    # For treatment variants: find the direct parent (base with or without sequential)
    if treatment_variant is not None and derivation_num is None:
        # Simple treatment: EXP-001_Desorption -> find EXP-001
        parent_id_to_find = base_id
        parent_id_norm = ''.join(ch for ch in parent_id_to_find.lower() if ch not in ['-', '_', ' '])
        parent = db.query(Experiment).filter(
            func.lower(
                func.replace(
                    func.replace(
                        func.replace(Experiment.experiment_id, '-', ''),
                        '_', ''
                    ),
                    ' ', ''
                )
            ) == parent_id_norm
        ).first()
        return parent
    
    elif treatment_variant is not None and derivation_num is not None:
        # Combined treatment: EXP-001-2_Desorption -> find EXP-001-2
        parent_id_to_find = f"{base_id}-{derivation_num}"
        parent_id_norm = ''.join(ch for ch in parent_id_to_find.lower() if ch not in ['-', '_', ' '])
        parent = db.query(Experiment).filter(
            func.lower(
                func.replace(
                    func.replace(
                        func.replace(Experiment.experiment_id, '-', ''),
                        '_', ''
                    ),
                    ' ', ''
                )
            ) == parent_id_norm
        ).first()
        return parent
    
    # For sequential experiments: find highest sequential < derivation_num, or base
    elif derivation_num is not None:
        # Query all experiments with the same base_experiment_id
        base_id_norm = ''.join(ch for ch in base_id.lower() if ch not in ['-', '_', ' '])
        candidates = db.query(Experiment).filter(
            func.lower(
                func.replace(
                    func.replace(
                        func.replace(Experiment.base_experiment_id, '-', ''),
                        '_', ''
                    ),
                    ' ', ''
                )
            ) == base_id_norm
        ).all()
        
        # Parse sequential numbers and find the highest one < derivation_num
        best_parent = None
        best_seq_num = -1
        
        for candidate in candidates:
            cand_base, cand_seq, cand_treatment, _cand_replicate_label = parse_experiment_id(candidate.experiment_id)
            
            # Skip if this is a treatment variant (we only want sequential or base)
            if cand_treatment is not None:
                continue
            
            # Check if this is the base (no sequential number)
            if cand_seq is None:
                if best_seq_num < 0:
                    best_parent = candidate
                    best_seq_num = 0  # Base has implicit seq 0
            # Check if sequential number is less than current and higher than best so far
            elif cand_seq < derivation_num and cand_seq > best_seq_num:
                best_parent = candidate
                best_seq_num = cand_seq
        
        return best_parent
    
    # Not a derivation (no sequential or treatment)
    return None


def update_experiment_lineage(db: Session, experiment):
    """
    Update the lineage fields (base_experiment_id, parent_experiment_fk,
    replicate_label, id_timepoint_days) for an experiment.

    Args:
        db: Database session
        experiment: The Experiment object to update

    Returns:
        True if lineage was updated, False if no update was needed

    Note:
        This function modifies the experiment object but does not commit the session.
        Treatment variants are tracked in the experiment_id but do not affect parent relationships.

        Classification:
        - Bare stem, or explicit "-0"/"-1" parent spelling (no treatment, no replicate
          letter): this row IS a group parent. base_experiment_id = stem,
          parent_experiment_fk = NULL.
        - Replicate member (replicate_label set): base_experiment_id = stem. Parent:
          a letter+sequential re-run with no treatment (e.g. SERUM_001a-2) resolves
          to the lettered sibling (SERUM_001a) when it exists; otherwise (plain
          replicate, treatment combo, or sibling missing) the group parent via
          find_replicate_group_parent (bare stem, then -0, then -1).
        - Everything else (sequential >= 2, treatment variants): unchanged existing
          behavior via get_or_find_parent_experiment.
    """
    if not experiment or not experiment.experiment_id:
        return False

    base_id, derivation_num, treatment_variant, replicate_label = parse_experiment_id(experiment.experiment_id)

    updated = False
    if experiment.replicate_label != replicate_label:
        experiment.replicate_label = replicate_label
        updated = True

    _, timepoint_days = split_timepoint_token(experiment.experiment_id.strip())
    if experiment.id_timepoint_days != timepoint_days:
        experiment.id_timepoint_days = timepoint_days
        updated = True

    is_parent_row = (
        treatment_variant is None
        and replicate_label is None
        and (derivation_num is None or derivation_num in (0, 1))
    )

    if is_parent_row:
        self_base_id = base_id or experiment.experiment_id
        if experiment.base_experiment_id != self_base_id:
            experiment.base_experiment_id = self_base_id
            updated = True
        if experiment.parent_experiment_fk is not None:
            experiment.parent_experiment_fk = None
            updated = True
        return updated

    # This is a derivation (sequential, treatment, and/or replicate)
    experiment.base_experiment_id = base_id

    if replicate_label is not None:
        parent = None
        if derivation_num is not None and treatment_variant is None:
            # P5 (issue #70): a sequential re-run of a lettered replicate
            # (e.g. SERUM_001a-2) links to the lettered sibling (SERUM_001a).
            # Any -N links to the letter itself (a-3 -> a, not a-2). Treatment
            # combos are excluded and keep the group-parent link below.
            parent = _find_experiment_by_exact_spelling(db, f"{base_id}{replicate_label}")
        if parent is None:
            # Plain replicate, or fallback when the lettered sibling doesn't
            # exist: pre-P5 group-parent resolution (bare stem, then -0, -1).
            parent = find_replicate_group_parent(db, base_id)
        # Assign via the relationship (not a raw `.id`): both resolvers can
        # return a row that is itself still pending in the current flush
        # (no primary key yet) — see _find_experiment_by_exact_spelling.
        parent = _reject_self_parent(experiment, parent)
        experiment.parent = parent
    else:
        parent = get_or_find_parent_experiment(db, experiment.experiment_id)
        parent = _reject_self_parent(experiment, parent)
        experiment.parent_experiment_fk = parent.id if parent else None

    return True


def update_orphaned_derivations(db: Session, base_experiment_id: str):
    """
    Update any derivations that reference this base experiment but don't have parent_experiment_fk set.

    This is called after a group parent is inserted (bare stem, or explicit -0/-1 spelling)
    to link any pre-existing derivations, including lettered replicates.

    Args:
        db: Database session
        base_experiment_id: The stem (e.g. "HPHT_MH_001") of the newly created group parent

    Returns:
        The number of derivations updated
    """
    from .models import Experiment

    if not base_experiment_id:
        return 0

    base_experiment = find_replicate_group_parent(db, base_experiment_id)
    if not base_experiment:
        return 0

    # A stem can have up to three parent spellings (bare, -0, -1) that may all
    # exist simultaneously. Whichever one wins precedence in find_replicate_group_parent
    # must not cause the OTHER spellings to be back-linked as if they were orphaned
    # children — they are all "the group parent", just written differently.
    #
    # Tracked by object (not just id): the row that triggered this call may itself
    # still be pending in the current flush (see _find_experiment_by_exact_spelling)
    # and so may not have a primary key yet. Filtering the SQL query by a bare id set
    # would silently break if that set ever contained a None id (SQL's three-valued
    # NOT IN logic treats a NULL member as "unknown" for every row, excluding
    # everything) — building the exclusion from real ids only, plus a Python-level
    # identity check below, avoids that trap.
    parent_alias_objs = {base_experiment}
    for alias_id in (base_experiment_id, f"{base_experiment_id}-0", f"{base_experiment_id}-1"):
        alias_row = _find_experiment_by_exact_spelling(db, alias_id)
        if alias_row:
            parent_alias_objs.add(alias_row)

    parent_alias_ids = {obj.id for obj in parent_alias_objs if obj.id is not None}

    # Find orphaned derivations (those with base_experiment_id matching but parent_experiment_fk
    # is NULL), excluding every parent-alias row for this stem.
    #
    # Issue #81 (I2): a letterless '-t<days>' timepoint vial (e.g. SERUM_001-t7)
    # is not a replicate-group member — it must never be adopted here just
    # because a later sibling insert (bare stem, -0, or -1) triggers this pass.
    # Lettered '-t' vials (replicate_label set) remain ordinary replicate
    # members and stay adoptable.
    query = db.query(Experiment).filter(
        Experiment.base_experiment_id == base_experiment_id,
        Experiment.parent_experiment_fk.is_(None),
        ~and_(
            Experiment.id_timepoint_days.isnot(None),
            Experiment.replicate_label.is_(None),
        ),
    )
    if parent_alias_ids:
        query = query.filter(Experiment.id.notin_(parent_alias_ids))
    orphaned = [row for row in query.all() if row not in parent_alias_objs]

    count = 0
    for derivation in orphaned:
        # Assign via the ORM relationship, not a raw `.id`, so SQLAlchemy's
        # dependency-ordered flush can back-fill the FK even when base_experiment
        # is itself still pending (no primary key yet) in the current flush.
        derivation.parent = base_experiment
        count += 1

    return count


# Fields never copied when cloning conditions from a parent experiment.
_CONDITIONS_COPY_RESERVED = {"id", "experiment_id", "experiment_fk", "created_at", "updated_at"}
_CONDITIONS_COPY_BLACKLIST = {
    "catalyst", "catalyst_mass",
    "buffer_system", "buffer_concentration",
    "surfactant_type", "surfactant_concentration",
    "catalyst_percentage", "catalyst_ppm",
    "water_to_rock_ratio",  # Calculated field
    "ammonium_chloride_concentration",
}

# Derived/identity additive columns owned by the calc engine or the DB, never copied.
_ADDITIVE_COPY_RESERVED = {
    "id", "experiment_id", "created_at", "updated_at",
    "mass_in_grams", "moles_added", "final_concentration", "concentration_units",
    "elemental_metal_mass", "catalyst_percentage", "catalyst_ppm",
}


def _copy_conditions_from_parent(db: Session, parent, new_experiment, include_additives: bool):
    """Clone parent's ExperimentalConditions (and optionally chemical additives)
    onto new_experiment. Flushes; does not commit. Returns the new conditions
    row or None when the parent has no conditions."""
    from .models import ExperimentalConditions, ChemicalAdditive

    if not parent.conditions:
        return None

    updatable_attrs = {
        col.name for col in ExperimentalConditions.__table__.columns
        if col.name not in _CONDITIONS_COPY_RESERVED
        and col.name not in _CONDITIONS_COPY_BLACKLIST
    }
    new_conditions = ExperimentalConditions(
        experiment_id=new_experiment.experiment_id,
        experiment_fk=new_experiment.id,
    )
    for attr in updatable_attrs:
        parent_value = getattr(parent.conditions, attr, None)
        if parent_value is not None:
            setattr(new_conditions, attr, parent_value)
    db.add(new_conditions)
    db.flush()

    if include_additives:
        additive_attrs = {
            col.name for col in ChemicalAdditive.__table__.columns
            if col.name not in _ADDITIVE_COPY_RESERVED
        }
        for parent_additive in parent.conditions.chemical_additives:
            new_additive = ChemicalAdditive(experiment_id=new_conditions.id)
            for attr in additive_attrs:
                value = getattr(parent_additive, attr, None)
                if value is not None:
                    setattr(new_additive, attr, value)
            db.add(new_additive)
        db.flush()

    return new_conditions


def auto_create_treatment_experiment(
    db: Session,
    experiment_id: str,
    initial_note: str
) -> Optional['Experiment']:
    """
    Auto-create a treatment variant experiment if parent exists.
    Only works for treatment variants (_delimiter), not sequential (-delimiter).
    
    Args:
        db: Database session
        experiment_id: The experiment ID to create (must be a treatment variant)
        initial_note: Description to use as the first note
        
    Returns:
        The created Experiment object if successful, None if not a treatment or parent not found
        
    Note:
        - Only works for treatment variants (with _ delimiter)
        - Does NOT work for sequential experiments (with - delimiter)
        - Copies conditions from parent experiment
        - Sets status to COMPLETED
        - Uses current date/time
    """
    from .models import Experiment, ExperimentNotes
    from datetime import datetime

    base_id, derivation_num, treatment_variant, _replicate_label = parse_experiment_id(experiment_id)

    # Only auto-create treatment variants, not sequential experiments
    if treatment_variant is None:
        return None
    
    # Find the parent experiment
    parent = get_or_find_parent_experiment(db, experiment_id)
    if not parent:
        return None
    
    # Generate next experiment number
    last = db.query(Experiment).order_by(Experiment.experiment_number.desc()).first()
    next_experiment_number = 1 if last is None else int(last.experiment_number or 0) + 1
    
    # Create new experiment
    from database.models.enums import ExperimentStatus
    new_experiment = Experiment(
        experiment_number=next_experiment_number,
        experiment_id=experiment_id,
        sample_id=parent.sample_id,
        researcher=parent.researcher,
        status=ExperimentStatus.COMPLETED,
        date=datetime.now(),
    )
    db.add(new_experiment)
    db.flush()  # Get the ID
    
    # Add initial note
    if initial_note:
        note = ExperimentNotes(
            experiment_id=new_experiment.experiment_id,
            experiment_fk=new_experiment.id,
            note_text=initial_note,
            created_at=datetime.now()
        )
        db.add(note)
    
    # Copy conditions from parent
    _copy_conditions_from_parent(db, parent, new_experiment, include_additives=False)

    # Establish lineage
    update_experiment_lineage(db, new_experiment)
    db.flush()

    return new_experiment


def create_replicate_experiments(
    db: Session, base_experiment_id: str, count: int
) -> tuple[list['Experiment'], list[str]]:
    """Create `count` lettered replicate experiments under a base experiment.

    The base (replicate 0) experiment acts as the template: sample, researcher,
    date, conditions, and chemical additives are copied to each new replicate;
    per-vial actuals stay editable afterwards. Letters continue after any
    existing members (a, b already present -> c, d, ...). Lineage fields are
    wired by the before_flush listener. Flushes; the caller owns the commit.

    Returns (created_experiments, skipped_messages). Conflicting IDs are
    skipped with a message, not fatal (issue #70 locked decision 3).
    Raises LookupError when no parent/template experiment exists.
    """
    from .models import Experiment

    stem, _seq, _treat, _label = parse_experiment_id(base_experiment_id)
    stem = stem or base_experiment_id

    parent = find_replicate_group_parent(db, stem)
    if parent is None:
        raise LookupError(
            f"No parent experiment found for base '{stem}' — create the base experiment first"
        )

    existing_labels = {
        label for (label,) in db.query(Experiment.replicate_label)
        .filter(Experiment.base_experiment_id == stem,
                Experiment.replicate_label.isnot(None))
        .all()
    }

    candidates = [c for c in "abcdefghijklmnopqrstuvwxyz" if c not in existing_labels]
    created: list[Experiment] = []
    skipped: list[str] = []
    if len(candidates) < count:
        skipped.append(
            f"Only {len(candidates)} replicate letters remain for '{stem}' "
            f"(requested {count}); creating {len(candidates)}."
        )

    last = db.query(Experiment).order_by(Experiment.experiment_number.desc()).first()
    next_number = 1 if last is None else int(last.experiment_number or 0) + 1

    for letter in candidates[:count]:
        new_id = f"{stem}{letter}"
        if _find_experiment_by_exact_spelling(db, new_id) is not None:
            skipped.append(f"'{new_id}' already exists — skipped, not overwritten.")
            continue
        new_experiment = Experiment(
            experiment_number=next_number,
            experiment_id=new_id,
            sample_id=parent.sample_id,
            researcher=parent.researcher,
            status=parent.status,
            date=parent.date,
        )
        next_number += 1
        db.add(new_experiment)
        db.flush()  # assigns PK + triggers lineage wiring via before_flush

        new_conditions = _copy_conditions_from_parent(
            db, parent, new_experiment, include_additives=True
        )
        if new_conditions is not None:
            from backend.services.calculations.registry import recalculate
            recalculate(new_conditions, db)
            for additive in new_conditions.chemical_additives:
                recalculate(additive, db)
            db.flush()

        created.append(new_experiment)

    return created, skipped

