"""
Data migration to establish experiment lineage for existing experiments.

This migration:
1. Parses all experiment IDs to identify derivations (e.g., "HPHT_MH_001-2")
2. Sets the base_experiment_id field for all derivations
3. Establishes parent_experiment_fk relationships where base experiments exist
4. Handles orphaned derivations (where base doesn't exist yet)
5. Tracks treatment variants (e.g., "HPHT_MH_001_Desorption")

Also includes fix_stale_lineage(), a targeted repair for experiments where
base_experiment_id was set under a prior naming convention and no longer matches
what parse_experiment_id computes from the current experiment_id. The known case
is CF-NNN experiments (e.g. CF-015) that were originally named CF_NNN; the old
underscore-based parser set base_experiment_id='CF' for all of them instead of
pointing each one to itself.

Run with:
    python database/data_migrations/establish_experiment_lineage_006.py
or:
    python database/data_migrations/establish_experiment_lineage_006.py --dry-run

To run only the stale-lineage fix:
    python database/data_migrations/establish_experiment_lineage_006.py --fix-stale
    python database/data_migrations/establish_experiment_lineage_006.py --fix-stale --dry-run
"""
import sys
import os

# Add parent directory to path to allow imports when run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from database import SessionLocal
from database.models import Experiment
from database.lineage_utils import parse_experiment_id, get_or_find_parent_experiment


def establish_experiment_lineage(dry_run: bool = False) -> dict:
    """
    Establish lineage relationships for all existing experiments.
    
    Args:
        dry_run: If True, rollback changes instead of committing
        
    Returns:
        A dictionary with migration statistics
    """
    db = SessionLocal()
    summary = {
        "experiments_scanned": 0,
        "derivations_found": 0,
        "parents_linked": 0,
        "orphaned_derivations": 0,
        "errors": 0,
    }
    
    try:
        # Get all experiments
        experiments = db.query(Experiment).all()
        summary["experiments_scanned"] = len(experiments)
        
        print(f"Scanning {summary['experiments_scanned']} experiments...")
        
        # First pass: Parse IDs and set base_experiment_id
        for exp in experiments:
            try:
                if not exp.experiment_id:
                    continue
                
                base_id, derivation_num, treatment_variant = parse_experiment_id(exp.experiment_id)
                
                if derivation_num is not None:
                    # This is a derivation (sequential run)
                    summary["derivations_found"] += 1
                    exp.base_experiment_id = base_id
                    if treatment_variant:
                        print(f"  Found derivation with treatment: {exp.experiment_id} -> base: {base_id}, treatment: {treatment_variant}")
                    else:
                        print(f"  Found derivation: {exp.experiment_id} -> base: {base_id}")
                else:
                    # This is a base experiment (or treatment-only variant), ensure self-referential lineage
                    exp.base_experiment_id = base_id or exp.experiment_id
                    exp.parent_experiment_fk = None
                    if treatment_variant:
                        print(f"  Found treatment variant (no parent): {exp.experiment_id} -> treatment: {treatment_variant}")
            
            except Exception as e:
                summary["errors"] += 1
                print(f"  Error processing {exp.experiment_id}: {e}")
        
        # Commit first pass
        if not dry_run:
            db.commit()
        else:
            db.flush()
        
        # Second pass: Resolve parent relationships
        print("\nResolving parent relationships...")
        derivations = db.query(Experiment).filter(
            Experiment.base_experiment_id.isnot(None)
        ).all()
        
        for deriv in derivations:
            try:
                parent = get_or_find_parent_experiment(db, deriv.experiment_id)
                
                if parent:
                    deriv.parent_experiment_fk = parent.id
                    summary["parents_linked"] += 1
                    print(f"  Linked {deriv.experiment_id} to parent {parent.experiment_id}")
                else:
                    summary["orphaned_derivations"] += 1
                    print(f"  Warning: Orphaned derivation {deriv.experiment_id} (base '{deriv.base_experiment_id}' not found)")
            
            except Exception as e:
                summary["errors"] += 1
                print(f"  Error linking parent for {deriv.experiment_id}: {e}")
        
        # Final commit or rollback
        if dry_run:
            print("\n=== DRY RUN: Rolling back changes ===")
            db.rollback()
        else:
            db.commit()
            print("\n=== Changes committed ===")
        
        return summary
    
    except Exception as e:
        print(f"\nCritical error during migration: {e}")
        db.rollback()
        raise
    
    finally:
        db.close()


def fix_stale_lineage(dry_run: bool = False) -> dict:
    """
    Repair experiments where base_experiment_id is stale from a prior naming convention.

    Scans every experiment and compares the stored base_experiment_id against what
    parse_experiment_id would compute today.  Any mismatch is corrected.  For base
    experiments (no derivation number) it also clears any stale parent_experiment_fk.

    The primary known case: CF-NNN experiments (CF-015, CF-014, CF-01, …) were
    originally uploaded as CF_NNN.  The old underscore parser treated the numeric
    suffix as a derivation index and wrote base_experiment_id='CF' for all of them.
    After renaming to CF-NNN the stored values were never recomputed, so the window
    function in v_results_scalar partitions CF-015 under 'CF' while CF-015-2 and
    CF-015-3 (created post-rename) sit under 'CF-015'.  The cumulative Fe-to-H2
    sum therefore never accumulates across the flush series.

    Args:
        dry_run: If True, print what would change but roll back without committing.

    Returns:
        A dict with counts: experiments_scanned, mismatches_found,
        base_id_fixed, parent_fk_cleared, errors.
    """
    db = SessionLocal()
    summary = {
        "experiments_scanned": 0,
        "mismatches_found": 0,
        "base_id_fixed": 0,
        "parent_fk_cleared": 0,
        "errors": 0,
    }

    try:
        experiments = db.query(Experiment).all()
        summary["experiments_scanned"] = len(experiments)

        print(f"Scanning {summary['experiments_scanned']} experiments for stale lineage...")

        for exp in experiments:
            if not exp.experiment_id:
                continue
            try:
                base_id, derivation_num, treatment_variant = parse_experiment_id(exp.experiment_id)
                expected_base = base_id or exp.experiment_id

                if exp.base_experiment_id != expected_base:
                    summary["mismatches_found"] += 1
                    print(
                        f"  MISMATCH {exp.experiment_id}: "
                        f"base_experiment_id {exp.base_experiment_id!r} -> {expected_base!r}"
                    )
                    exp.base_experiment_id = expected_base
                    summary["base_id_fixed"] += 1

                # Base experiments must not carry a parent FK
                if derivation_num is None and treatment_variant is None:
                    if exp.parent_experiment_fk is not None:
                        print(
                            f"  CLEAR parent_fk {exp.experiment_id}: "
                            f"parent_experiment_fk {exp.parent_experiment_fk} -> NULL"
                        )
                        exp.parent_experiment_fk = None
                        summary["parent_fk_cleared"] += 1

            except Exception as e:
                summary["errors"] += 1
                print(f"  Error processing {exp.experiment_id}: {e}")

        if dry_run:
            print("\n=== DRY RUN: Rolling back changes ===")
            db.rollback()
        else:
            db.commit()
            print("\n=== Changes committed ===")

        return summary

    except Exception as e:
        print(f"\nCritical error: {e}")
        db.rollback()
        raise

    finally:
        db.close()


def run_migration():
    """
    Entry point for scripts/run_data_migration.py runner.

    Runs the full lineage establishment followed by the stale-lineage fix so
    that both passes execute atomically when this file is invoked via the
    standard migration runner.
    """
    print("=" * 60)
    print("ESTABLISHING EXPERIMENT LINEAGE")
    print("=" * 60)

    summary = establish_experiment_lineage(dry_run=False)

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print(f"Experiments scanned:     {summary['experiments_scanned']}")
    print(f"Derivations found:       {summary['derivations_found']}")
    print(f"Parents linked:          {summary['parents_linked']}")
    print(f"Orphaned derivations:    {summary['orphaned_derivations']}")
    print(f"Errors:                  {summary['errors']}")
    print("=" * 60)

    if summary["orphaned_derivations"] > 0:
        print("\nNote: Orphaned derivations have their base_experiment_id set")
        print("but parent_experiment_fk is NULL because the base experiment")
        print("doesn't exist. When the base experiment is created, the relationship")
        print("will be automatically established by the event listeners.")

    print("\n" + "=" * 60)
    print("FIXING STALE LINEAGE")
    print("=" * 60)

    fix_summary = fix_stale_lineage(dry_run=False)

    print("\n" + "=" * 60)
    print("STALE LINEAGE FIX COMPLETE")
    print("=" * 60)
    print(f"Experiments scanned:     {fix_summary['experiments_scanned']}")
    print(f"Mismatches found:        {fix_summary['mismatches_found']}")
    print(f"base_experiment_id fixed:{fix_summary['base_id_fixed']}")
    print(f"parent_fk cleared:       {fix_summary['parent_fk_cleared']}")
    print(f"Errors:                  {fix_summary['errors']}")
    print("=" * 60)

    return True


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    fix_stale_only = "--fix-stale" in sys.argv

    if dry_run:
        print("Running in DRY RUN mode (no changes will be saved)\n")

    if fix_stale_only:
        print("=" * 60)
        print("FIXING STALE LINEAGE (targeted pass only)")
        print("=" * 60)
        summary = fix_stale_lineage(dry_run=dry_run)
        print("\nSummary:")
        print(f"  Experiments scanned:      {summary['experiments_scanned']}")
        print(f"  Mismatches found:         {summary['mismatches_found']}")
        print(f"  base_experiment_id fixed: {summary['base_id_fixed']}")
        print(f"  parent_fk cleared:        {summary['parent_fk_cleared']}")
        print(f"  Errors:                   {summary['errors']}")
    else:
        summary = establish_experiment_lineage(dry_run=dry_run)
        print("\nLineage summary:")
        print(summary)

        print()
        fix_summary = fix_stale_lineage(dry_run=dry_run)
        print("\nStale-lineage fix summary:")
        print(fix_summary)

