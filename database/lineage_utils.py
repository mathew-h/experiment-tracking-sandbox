from __future__ import annotations

"""
Utility functions for managing experiment lineage.

This module provides functions to parse experiment IDs, identify derivations,
and establish parent-child relationships between experiments.

Supports hybrid delimiter system:
- Hyphen-NUMBER for sequential lineage (e.g., -2, -3)
- Underscore-TEXT for treatment variants (e.g., _Desorption)
"""
from typing import Optional, Tuple, TYPE_CHECKING
from sqlalchemy.orm import Session
from sqlalchemy import func

if TYPE_CHECKING:
    from .models import Experiment


def parse_experiment_id(experiment_id: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    Parse an experiment ID to extract the base ID, derivation number, and treatment variant.
    
    Uses hybrid delimiter system:
    - Hyphen-NUMBER for sequential lineage (e.g., -2, -3)
    - Underscore-TEXT for treatment variants (e.g., _Desorption)
    
    Supports both 2-part (TYPE_INDEX) and 3-part (TYPE_INITIALS_INDEX) formats.
    
    Args:
        experiment_id: The experiment ID to parse (e.g., "HPHT_MH_001-2_Desorption" or "HPHT_001-2_Desorption")
        
    Returns:
        A tuple of (base_experiment_id, derivation_number, treatment_variant)
        - For "HPHT_MH_001-2": returns ("HPHT_MH_001", 2, None)
        - For "HPHT_001-2": returns ("HPHT_001", 2, None)
        - For "HPHT_MH_001": returns ("HPHT_MH_001", None, None)
        - For "HPHT_001": returns ("HPHT_001", None, None)
        - For "HPHT_MH_001_Desorption": returns ("HPHT_MH_001", None, "Desorption")
        - For "HPHT_001_Desorption": returns ("HPHT_001", None, "Desorption")
        - For "HPHT_MH_001-2_Desorption": returns ("HPHT_MH_001", 2, "Desorption")
        - For "HPHT_001-2_Desorption": returns ("HPHT_001", 2, "Desorption")
        
    Examples:
        >>> parse_experiment_id("HPHT_MH_001-2")
        ("HPHT_MH_001", 2, None)
        >>> parse_experiment_id("HPHT_001-2")
        ("HPHT_001", 2, None)
        >>> parse_experiment_id("HPHT_MH_001")
        ("HPHT_MH_001", None, None)
        >>> parse_experiment_id("HPHT_001")
        ("HPHT_001", None, None)
        >>> parse_experiment_id("HPHT_MH_001_Desorption")
        ("HPHT_MH_001", None, "Desorption")
        >>> parse_experiment_id("HPHT_001_Desorption")
        ("HPHT_001", None, "Desorption")
        >>> parse_experiment_id("HPHT_MH_001-2_Desorption")
        ("HPHT_MH_001", 2, "Desorption")
        >>> parse_experiment_id("HPHT_001-2_Desorption")
        ("HPHT_001", 2, "Desorption")
    """
    if not experiment_id or not isinstance(experiment_id, str):
        return None, None, None
    
    experiment_id = experiment_id.strip()
    if not experiment_id:
        return None, None, None
    
    treatment_variant = None
    derivation_num = None
    base_id = experiment_id
    
    # First, extract sequential number (hyphen-NUMBER pattern from the end)
    # This must be done before treatment detection to avoid confusion
    if '-' in experiment_id:
        hyphen_parts = experiment_id.rsplit('-', 1)
        if len(hyphen_parts) == 2 and hyphen_parts[-1].isdigit():
            derivation_num = int(hyphen_parts[-1])
            base_id = hyphen_parts[0]
    
    # Now check for treatment variant in the remaining base_id
    # Split by underscore to detect if last part is a treatment
    parts = base_id.split('_')
    
    # Determine expected base format by checking part count
    # After removing sequential, we should have:
    # - 2 parts for TYPE_INDEX format (e.g., HPHT_001)
    # - 3 parts for TYPE_INITIALS_INDEX format (e.g., Serum_MH_101)
    # If we have more parts than expected, the last part is likely a treatment
    
    if len(parts) > 2:
        # Could be 2-part format with treatment, or 3-part format (with or without treatment)
        potential_treatment = parts[-1]
        
        # Check if last part looks like a treatment (not all numeric)
        if not potential_treatment.isdigit():
            # Last part is not numeric, likely a treatment
            # If we have 3+ parts and last is non-numeric, it's a treatment
            if len(parts) >= 3:
                treatment_variant = potential_treatment
                base_id = '_'.join(parts[:-1])
    
    return base_id, derivation_num, treatment_variant


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
    
    base_id, derivation_num, treatment_variant = parse_experiment_id(experiment_id)
    
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
            cand_base, cand_seq, cand_treatment = parse_experiment_id(candidate.experiment_id)
            
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
    Update the lineage fields (base_experiment_id, parent_experiment_fk) for an experiment.
    
    Args:
        db: Database session
        experiment: The Experiment object to update
        
    Returns:
        True if lineage was updated, False if no update was needed
        
    Note:
        This function modifies the experiment object but does not commit the session.
        Treatment variants are tracked in the experiment_id but do not affect parent relationships.
    """
    if not experiment or not experiment.experiment_id:
        return False
    
    base_id, derivation_num, treatment_variant = parse_experiment_id(experiment.experiment_id)
    
    # If this is not a derivation (no sequential AND no treatment), ensure base_experiment_id references itself
    if derivation_num is None and treatment_variant is None:
        updated = False
        self_base_id = base_id or experiment.experiment_id
        if experiment.base_experiment_id != self_base_id:
            experiment.base_experiment_id = self_base_id
            updated = True
        if experiment.parent_experiment_fk is not None:
            experiment.parent_experiment_fk = None
            updated = True
        return updated
    
    # This is a derivation (has sequential OR treatment), set base_experiment_id
    experiment.base_experiment_id = base_id
    
    # Try to find and set the parent
    parent = get_or_find_parent_experiment(db, experiment.experiment_id)
    if parent:
        experiment.parent_experiment_fk = parent.id
    else:
        # Parent doesn't exist yet, leave parent_experiment_fk as None
        experiment.parent_experiment_fk = None
    
    return True


def update_orphaned_derivations(db: Session, base_experiment_id: str):
    """
    Update any derivations that reference this base experiment but don't have parent_experiment_fk set.
    
    This is called after a base experiment is inserted to link any pre-existing derivations.
    
    Args:
        db: Database session
        base_experiment_id: The experiment_id of the newly created base experiment
        
    Returns:
        The number of derivations updated
    """
    from .models import Experiment
    
    if not base_experiment_id:
        return 0
    
    # Find the base experiment
    base_id_norm = ''.join(ch for ch in base_experiment_id.lower() if ch not in ['-', '_', ' '])
    base_experiment = db.query(Experiment).filter(
        func.lower(
            func.replace(
                func.replace(
                    func.replace(Experiment.experiment_id, '-', ''),
                    '_', ''
                ),
                ' ', ''
            )
        ) == base_id_norm
    ).first()
    
    if not base_experiment:
        return 0
    
    # Find orphaned derivations (those with base_experiment_id matching but parent_experiment_fk is NULL)
    orphaned = db.query(Experiment).filter(
        Experiment.base_experiment_id == base_experiment_id,
        Experiment.parent_experiment_fk.is_(None),
        Experiment.id != base_experiment.id
    ).all()
    
    count = 0
    for derivation in orphaned:
        derivation.parent_experiment_fk = base_experiment.id
        count += 1
    
    return count


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
    from .models import Experiment, ExperimentNotes, ExperimentalConditions
    from datetime import datetime
    
    base_id, derivation_num, treatment_variant = parse_experiment_id(experiment_id)
    
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
    if parent.conditions:
        # Define fields that should not be copied (PKs, FKs, metadata, calculated)
        reserved = {"id", "experiment_id", "experiment_fk", "created_at", "updated_at"}
        blacklist = {
            "catalyst", "catalyst_mass",
            "buffer_system", "buffer_concentration",
            "surfactant_type", "surfactant_concentration",
            "catalyst_percentage", "catalyst_ppm",
            "water_to_rock_ratio",  # Calculated field
            "ammonium_chloride_concentration",
        }
        updatable_attrs = {
            col.name for col in ExperimentalConditions.__table__.columns
            if col.name not in reserved and col.name not in blacklist
        }
        
        new_conditions = ExperimentalConditions(
            experiment_id=new_experiment.experiment_id,
            experiment_fk=new_experiment.id,
        )
        
        # Copy all updatable fields from parent
        for attr in updatable_attrs:
            parent_value = getattr(parent.conditions, attr, None)
            if parent_value is not None:
                setattr(new_conditions, attr, parent_value)
        
        db.add(new_conditions)
        db.flush()
    
    # Establish lineage
    update_experiment_lineage(db, new_experiment)
    db.flush()
    
    return new_experiment

