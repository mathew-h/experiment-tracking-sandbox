"""
Data Migration: Merge Duplicate Sample IDs (007)

This script identifies and merges duplicate sample IDs that differ only in formatting
(e.g., "rock-001", "ROCK-001", "rock 001", "rock_001").

It will:
1. Identify groups of duplicate samples based on normalized IDs
2. Choose a primary sample (preferably in canonical format: UPPERCASE, no spaces/underscores)
3. Migrate all foreign key references to the primary sample
4. Merge metadata (keeping non-null values when possible)
5. Delete duplicate samples

Run this after deploying the fixed rock_inventory.py to prevent future duplicates.
"""

import sys
import os
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy import func, text
from sqlalchemy.orm import Session
from database import SessionLocal, SampleInfo, Experiment, ExternalAnalysis, SamplePhotos
from database.models.analysis import ElementalAnalysis
from database.models.xrd import XRDPhase


def normalize_sample_id(sample_id: str) -> str:
    """Normalize sample_id for comparison (lowercase, no hyphens/underscores/spaces)."""
    return ''.join(ch for ch in sample_id.lower() if ch not in ['-', '_', ' '])


def get_canonical_format(sample_id: str) -> str:
    """Convert to canonical format: UPPERCASE, no spaces/underscores, preserve hyphens."""
    return sample_id.upper().replace(' ', '').replace('_', '')


def find_duplicate_groups(db: Session) -> Dict[str, List[str]]:
    """
    Find groups of duplicate sample IDs.
    
    Returns:
        Dict mapping normalized_id -> list of actual sample_ids
    """
    all_samples = db.query(SampleInfo.sample_id).all()
    
    groups = defaultdict(list)
    for (sample_id,) in all_samples:
        normalized = normalize_sample_id(sample_id)
        groups[normalized].append(sample_id)
    
    # Filter to only duplicates (groups with more than one member)
    duplicates = {norm_id: ids for norm_id, ids in groups.items() if len(ids) > 1}
    
    return duplicates


def choose_primary_sample(sample_ids: List[str], db: Session) -> str:
    """
    Choose the best sample_id to keep as primary.
    
    Priority:
    1. Canonical format (UPPERCASE, no spaces/underscores)
    2. Has most foreign key references (experiments, analyses, photos)
    3. Alphabetically first
    """
    def is_canonical(sid: str) -> bool:
        """Check if already in canonical format."""
        canonical = get_canonical_format(sid)
        return sid == canonical
    
    def count_references(sid: str) -> int:
        """Count how many foreign key references this sample has."""
        exp_count = db.query(Experiment).filter(Experiment.sample_id == sid).count()
        analysis_count = db.query(ExternalAnalysis).filter(ExternalAnalysis.sample_id == sid).count()
        photo_count = db.query(SamplePhotos).filter(SamplePhotos.sample_id == sid).count()
        elem_count = db.query(ElementalAnalysis).filter(ElementalAnalysis.sample_id == sid).count()
        xrd_count = db.query(XRDPhase).filter(XRDPhase.sample_id == sid).count()
        return exp_count + analysis_count + photo_count + elem_count + xrd_count
    
    # Score each sample_id
    scored = []
    for sid in sample_ids:
        score = (
            is_canonical(sid),  # Prefer canonical format
            count_references(sid),  # Prefer more references
            -len(sid),  # Prefer shorter (negative for descending)
            sid  # Alphabetically
        )
        scored.append((score, sid))
    
    # Return the best one
    scored.sort(reverse=True)
    return scored[0][1]


def merge_sample_metadata(primary: SampleInfo, duplicates: List[SampleInfo]) -> None:
    """
    Merge metadata from duplicate samples into primary.
    For each field, keep non-null values, preferring primary if it has a value.
    """
    fields = ['rock_classification', 'state', 'country', 'locality', 
              'latitude', 'longitude', 'description', 'characterized']
    
    for field in fields:
        primary_val = getattr(primary, field)
        if primary_val is None or (isinstance(primary_val, str) and not primary_val.strip()):
            # Primary has no value, try to get from duplicates
            for dup in duplicates:
                dup_val = getattr(dup, field)
                if dup_val is not None and (not isinstance(dup_val, str) or dup_val.strip()):
                    setattr(primary, field, dup_val)
                    print(f"    - Merged {field}: {dup_val} from {dup.sample_id}")
                    break


def migrate_foreign_keys(primary_id: str, duplicate_ids: List[str], db: Session) -> Tuple[int, int, int, int, int]:
    """
    Migrate all foreign key references from duplicates to primary.
    
    Returns:
        (experiments_migrated, analyses_migrated, photos_migrated, elemental_migrated, xrd_migrated)
    """
    exp_count = analysis_count = photo_count = elem_count = xrd_count = 0
    
    for dup_id in duplicate_ids:
        # Migrate Experiments
        experiments = db.query(Experiment).filter(Experiment.sample_id == dup_id).all()
        for exp in experiments:
            exp.sample_id = primary_id
            exp_count += 1
        
        # Migrate ExternalAnalysis (check for duplicates first)
        analyses = db.query(ExternalAnalysis).filter(ExternalAnalysis.sample_id == dup_id).all()
        for analysis in analyses:
            # Check if primary already has this exact analysis
            existing = db.query(ExternalAnalysis).filter(
                ExternalAnalysis.sample_id == primary_id,
                ExternalAnalysis.analysis_type == analysis.analysis_type,
                ExternalAnalysis.pxrf_reading_no == analysis.pxrf_reading_no
            ).first()
            
            if existing:
                # Delete duplicate analysis
                db.delete(analysis)
                print(f"    - Removed duplicate analysis: {analysis.analysis_type} for {dup_id}")
            else:
                # Migrate to primary
                analysis.sample_id = primary_id
                analysis_count += 1
        
        # Migrate SamplePhotos (check for duplicates)
        photos = db.query(SamplePhotos).filter(SamplePhotos.sample_id == dup_id).all()
        for photo in photos:
            existing_photo = db.query(SamplePhotos).filter(
                SamplePhotos.sample_id == primary_id,
                SamplePhotos.file_name == photo.file_name
            ).first()
            
            if existing_photo:
                # Keep newer photo
                if photo.created_at > existing_photo.created_at:
                    existing_photo.file_path = photo.file_path
                    existing_photo.file_type = photo.file_type
                    print(f"    - Updated photo: {photo.file_name}")
                db.delete(photo)
            else:
                photo.sample_id = primary_id
                photo_count += 1
        
        # Migrate ElementalAnalysis (check for duplicates)
        elem_results = db.query(ElementalAnalysis).filter(ElementalAnalysis.sample_id == dup_id).all()
        for elem in elem_results:
            existing_elem = db.query(ElementalAnalysis).filter(
                ElementalAnalysis.sample_id == primary_id,
                ElementalAnalysis.analyte_id == elem.analyte_id
            ).first()
            
            if existing_elem:
                # Keep the more recent or non-null value
                if elem.analyte_composition is not None:
                    if existing_elem.analyte_composition is None or elem.updated_at > existing_elem.updated_at:
                        existing_elem.analyte_composition = elem.analyte_composition
                        print(f"    - Updated elemental result for analyte {elem.analyte_id}")
                db.delete(elem)
            else:
                elem.sample_id = primary_id
                elem_count += 1
        
        # Migrate XRDPhase (check for duplicates)
        xrd_phases = db.query(XRDPhase).filter(XRDPhase.sample_id == dup_id).all()
        for xrd in xrd_phases:
            existing_xrd = db.query(XRDPhase).filter(
                XRDPhase.sample_id == primary_id,
                XRDPhase.mineral_name == xrd.mineral_name
            ).first()
            
            if existing_xrd:
                # Keep the more recent or non-null value
                if xrd.amount is not None:
                    if existing_xrd.amount is None or xrd.updated_at > existing_xrd.updated_at:
                        existing_xrd.amount = xrd.amount
                        print(f"    - Updated XRD phase for mineral {xrd.mineral_name}")
                db.delete(xrd)
            else:
                xrd.sample_id = primary_id
                xrd_count += 1
    
    return exp_count, analysis_count, photo_count, elem_count, xrd_count


def merge_duplicates(db: Session, dry_run: bool = True) -> None:
    """
    Main function to identify and merge duplicate samples.
    
    Args:
        db: Database session
        dry_run: If True, only report what would be done without making changes
    """
    print("\n" + "="*80)
    print("DUPLICATE SAMPLE MERGER")
    print("="*80)
    print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'LIVE (changes will be applied)'}")
    print("="*80 + "\n")
    
    # Find duplicate groups
    print("Step 1: Finding duplicate sample IDs...")
    duplicate_groups = find_duplicate_groups(db)
    
    if not duplicate_groups:
        print("✓ No duplicate samples found!")
        return
    
    print(f"✗ Found {len(duplicate_groups)} groups of duplicates:\n")
    
    total_samples_to_delete = 0
    total_migrations = {'experiments': 0, 'analyses': 0, 'photos': 0, 'elemental': 0, 'xrd': 0}
    
    # Process each group
    for norm_id, sample_ids in duplicate_groups.items():
        print(f"\nGroup: {norm_id}")
        print(f"  Duplicates: {sample_ids}")
        
        # Choose primary
        primary_id = choose_primary_sample(sample_ids, db)
        duplicate_ids = [sid for sid in sample_ids if sid != primary_id]
        
        print(f"  → Primary: {primary_id}")
        print(f"  → To merge: {duplicate_ids}")
        
        if not dry_run:
            # Get sample objects
            primary_sample = db.query(SampleInfo).filter(SampleInfo.sample_id == primary_id).first()
            duplicate_samples = [db.query(SampleInfo).filter(SampleInfo.sample_id == dup_id).first() 
                               for dup_id in duplicate_ids]
            
            # Merge metadata
            print(f"  Merging metadata...")
            merge_sample_metadata(primary_sample, duplicate_samples)
            
            # Migrate foreign keys
            print(f"  Migrating foreign key references...")
            exp, ana, pho, ele, xrd = migrate_foreign_keys(primary_id, duplicate_ids, db)
            total_migrations['experiments'] += exp
            total_migrations['analyses'] += ana
            total_migrations['photos'] += pho
            total_migrations['elemental'] += ele
            total_migrations['xrd'] += xrd
            
            print(f"    - Migrated {exp} experiments, {ana} analyses, {pho} photos, {ele} elemental, {xrd} XRD phases")
            
            # Delete duplicate samples
            for dup_sample in duplicate_samples:
                db.delete(dup_sample)
                total_samples_to_delete += 1
                print(f"  ✓ Deleted duplicate: {dup_sample.sample_id}")
        else:
            total_samples_to_delete += len(duplicate_ids)
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Duplicate groups found: {len(duplicate_groups)}")
    print(f"Samples to delete: {total_samples_to_delete}")
    
    if not dry_run:
        print(f"Experiments migrated: {total_migrations['experiments']}")
        print(f"Analyses migrated: {total_migrations['analyses']}")
        print(f"Photos migrated: {total_migrations['photos']}")
        print(f"Elemental results migrated: {total_migrations['elemental']}")
        print(f"XRD phases migrated: {total_migrations['xrd']}")
        
        try:
            db.commit()
            print("\n✓ Changes committed successfully!")
        except Exception as e:
            db.rollback()
            print(f"\n✗ Error committing changes: {e}")
            raise
    else:
        print("\nNo changes made (dry run mode)")
        print("Run with --apply to execute the merge")
    
    print("="*80 + "\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Merge duplicate sample IDs in the database')
    parser.add_argument('--apply', action='store_true', 
                       help='Apply changes (default is dry run)')
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        merge_duplicates(db, dry_run=not args.apply)
    finally:
        db.close()

