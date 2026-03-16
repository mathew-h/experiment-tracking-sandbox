"""
Diagnostic Script: Identify ALL Duplicate Sample IDs

This script provides detailed analysis of duplicate samples in the database,
showing exactly what duplicates exist and how they differ.
"""

import sys
import os
from typing import List, Dict
from collections import defaultdict

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy import func
from database import SessionLocal, SampleInfo, Experiment, ExternalAnalysis, SamplePhotos
from database.models.analysis import ElementalAnalysis
from database.models.xrd import XRDPhase


def normalize_sample_id(sample_id: str) -> str:
    """Normalize sample_id for comparison (lowercase, no hyphens/underscores/spaces)."""
    return ''.join(ch for ch in sample_id.lower() if ch not in ['-', '_', ' '])


def find_all_duplicates(db):
    """Find and display ALL duplicate sample IDs with detailed info."""
    
    print("\n" + "="*100)
    print("DUPLICATE SAMPLE ANALYSIS")
    print("="*100 + "\n")
    
    # Get all samples
    all_samples = db.query(SampleInfo.sample_id).all()
    total_samples = len(all_samples)
    print(f"Total samples in database: {total_samples}\n")
    
    # Group by normalized ID
    groups = defaultdict(list)
    for (sample_id,) in all_samples:
        normalized = normalize_sample_id(sample_id)
        groups[normalized].append(sample_id)
    
    # Find duplicates
    duplicates = {norm_id: ids for norm_id, ids in groups.items() if len(ids) > 1}
    unique_samples = len(groups)
    duplicate_count = sum(len(ids) - 1 for ids in duplicates.values())
    
    print(f"Unique samples (after normalization): {unique_samples}")
    print(f"Duplicate groups: {len(duplicates)}")
    print(f"Extra duplicate records: {duplicate_count}")
    print(f"Expected sample count after merge: {unique_samples}\n")
    
    if not duplicates:
        print("✓ No duplicates found!")
        return
    
    print("="*100)
    print("DUPLICATE GROUPS (sorted by count)")
    print("="*100 + "\n")
    
    # Sort by number of duplicates
    sorted_groups = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)
    
    for norm_id, sample_ids in sorted_groups:
        print(f"\nNormalized ID: '{norm_id}'")
        print(f"  Count: {len(sample_ids)} duplicates")
        print(f"  Actual IDs:")
        
        for sid in sorted(sample_ids):
            # Get reference counts
            sample = db.query(SampleInfo).filter(SampleInfo.sample_id == sid).first()
            exp_count = db.query(Experiment).filter(Experiment.sample_id == sid).count()
            analysis_count = db.query(ExternalAnalysis).filter(ExternalAnalysis.sample_id == sid).count()
            photo_count = db.query(SamplePhotos).filter(SamplePhotos.sample_id == sid).count()
            elem_count = db.query(ElementalAnalysis).filter(ElementalAnalysis.sample_id == sid).count()
            xrd_count = db.query(XRDPhase).filter(XRDPhase.sample_id == sid).count()
            
            total_refs = exp_count + analysis_count + photo_count + elem_count + xrd_count
            
            info_parts = []
            if sample.rock_classification:
                info_parts.append(f"type={sample.rock_classification}")
            if sample.locality:
                info_parts.append(f"loc={sample.locality}")
            if total_refs > 0:
                ref_details = []
                if exp_count: ref_details.append(f"{exp_count}exp")
                if analysis_count: ref_details.append(f"{analysis_count}ana")
                if photo_count: ref_details.append(f"{photo_count}pho")
                if elem_count: ref_details.append(f"{elem_count}ele")
                if xrd_count: ref_details.append(f"{xrd_count}xrd")
                info_parts.append(f"refs={','.join(ref_details)}")
            
            info = f" [{', '.join(info_parts)}]" if info_parts else " [no data]"
            
            # Show character differences
            char_analysis = []
            if '-' in sid:
                char_analysis.append("has-hyphen")
            if '_' in sid:
                char_analysis.append("has_underscore")
            if ' ' in sid:
                char_analysis.append("has space")
            if sid != sid.upper():
                char_analysis.append("mixed/lowercase")
            if sid != sid.lower():
                char_analysis.append("has uppercase")
            
            char_info = f" ({', '.join(char_analysis)})" if char_analysis else ""
            
            print(f"    • '{sid}'{char_info}{info}")
    
    print("\n" + "="*100)
    print("SUMMARY BY CHARACTER DIFFERENCES")
    print("="*100 + "\n")
    
    # Analyze what's causing the duplicates
    case_diffs = 0
    separator_diffs = 0
    spacing_diffs = 0
    
    for norm_id, sample_ids in duplicates.items():
        # Check if difference is only case
        lowercase_forms = set(sid.lower() for sid in sample_ids)
        if len(lowercase_forms) == 1:
            case_diffs += 1
        
        # Check if difference is separators (- vs _)
        no_sep_forms = set(sid.replace('-', '').replace('_', '') for sid in sample_ids)
        if len(no_sep_forms) == 1:
            separator_diffs += 1
        
        # Check if difference is spacing
        no_space_forms = set(sid.replace(' ', '') for sid in sample_ids)
        if len(no_space_forms) == 1:
            spacing_diffs += 1
    
    print(f"Duplicates differing by:")
    print(f"  - Case only: {case_diffs}")
    print(f"  - Separators (- vs _): {separator_diffs}")
    print(f"  - Spacing: {spacing_diffs}")
    
    print("\n" + "="*100)
    print("ACTIONABLE ITEMS")
    print("="*100)
    print(f"\n1. Run merge script to consolidate {duplicate_count} duplicate records")
    print(f"2. This will reduce sample count from {total_samples} to {unique_samples}")
    print(f"\nCommand to merge (DRY RUN first):")
    print(f"  python database/data_migrations/merge_duplicate_samples_007.py")
    print(f"\nCommand to merge (APPLY changes):")
    print(f"  python database/data_migrations/merge_duplicate_samples_007.py --apply")
    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        find_all_duplicates(db)
    finally:
        db.close()
