"""
Data Migration: Normalize pXRF Reading Numbers (008)

This script fixes the float formatting issue where reading numbers are stored as
"1.0", "2.0", "34.0" instead of "1", "2", "34".

It will:
1. Normalize all reading_no values in pxrf_readings table
2. Normalize all pxrf_reading_no values in external_analyses table
3. Handle comma-separated values (e.g., "2.0,3.0,4.0" -> "2,3,4")

Run this after Excel uploads have created mismatched float-formatted reading numbers.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy.orm import Session
from database import SessionLocal
from database.models.analysis import PXRFReading, ExternalAnalysis


def normalize_reading_number(val: str) -> str:
    """
    Normalize a reading number or comma-separated list.
    Removes .0 suffix from float strings (e.g., "34.0" -> "34", "2.0,3.0,4.0" -> "2,3,4")
    """
    if not val or not val.strip():
        return val
    
    val_str = val.strip()
    
    # Handle comma-separated values
    if ',' in val_str:
        parts = []
        for part in val_str.split(','):
            part = part.strip()
            if part:
                # Convert "2.0" to "2"
                try:
                    if '.' in part and part.replace('.', '', 1).replace('-', '', 1).isdigit():
                        parts.append(str(int(float(part))))
                    else:
                        parts.append(part)
                except (ValueError, TypeError):
                    parts.append(part)
        return ','.join(parts)
    else:
        # Single value - convert "34.0" to "34"
        try:
            if '.' in val_str and val_str.replace('.', '', 1).replace('-', '', 1).isdigit():
                return str(int(float(val_str)))
        except (ValueError, TypeError):
            pass
        return val_str


def normalize_pxrf_data(db: Session, dry_run: bool = True) -> None:
    """
    Normalize all pXRF reading numbers in the database.
    
    Args:
        db: Database session
        dry_run: If True, only report what would be changed without making changes
    """
    print("\n" + "="*80)
    print("pXRF READING NUMBER NORMALIZER")
    print("="*80)
    print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'LIVE (changes will be applied)'}")
    print("="*80 + "\n")
    
    # Process PXRFReading table
    print("Step 1: Normalizing pxrf_readings.reading_no...")
    pxrf_readings = db.query(PXRFReading).all()
    pxrf_changes = []
    
    for reading in pxrf_readings:
        original = reading.reading_no
        normalized = normalize_reading_number(original)
        
        if original != normalized:
            pxrf_changes.append((original, normalized))
            if not dry_run:
                reading.reading_no = normalized
    
    if pxrf_changes:
        print(f"Found {len(pxrf_changes)} readings to normalize:")
        for old, new in pxrf_changes[:10]:  # Show first 10
            print(f"  '{old}' -> '{new}'")
        if len(pxrf_changes) > 10:
            print(f"  ... and {len(pxrf_changes) - 10} more")
    else:
        print("✓ All reading numbers already normalized")
    
    # Process ExternalAnalysis table
    print("\nStep 2: Normalizing external_analyses.pxrf_reading_no...")
    analyses = db.query(ExternalAnalysis).filter(
        ExternalAnalysis.pxrf_reading_no.isnot(None)
    ).all()
    analysis_changes = []
    
    for analysis in analyses:
        original = analysis.pxrf_reading_no
        normalized = normalize_reading_number(original)
        
        if original != normalized:
            analysis_changes.append((analysis.sample_id, original, normalized))
            if not dry_run:
                analysis.pxrf_reading_no = normalized
    
    if analysis_changes:
        print(f"Found {len(analysis_changes)} analyses to normalize:")
        for sample_id, old, new in analysis_changes[:10]:  # Show first 10
            print(f"  Sample {sample_id}: '{old}' -> '{new}'")
        if len(analysis_changes) > 10:
            print(f"  ... and {len(analysis_changes) - 10} more")
    else:
        print("✓ All analysis reading numbers already normalized")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"PXRFReading table: {len(pxrf_changes)} reading numbers to normalize")
    print(f"ExternalAnalysis table: {len(analysis_changes)} reading numbers to normalize")
    print(f"Total changes: {len(pxrf_changes) + len(analysis_changes)}")
    
    if not dry_run:
        if pxrf_changes or analysis_changes:
            try:
                db.commit()
                print("\n✓ Changes committed successfully!")
                print("\nRECOMMENDATION: Refresh your Power BI data to see the updated values")
            except Exception as e:
                db.rollback()
                print(f"\n✗ Error committing changes: {e}")
                raise
        else:
            print("\nNo changes needed")
    else:
        print("\nNo changes made (dry run mode)")
        print("Run with --apply to execute the normalization")
    
    print("="*80 + "\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Normalize pXRF reading numbers in the database')
    parser.add_argument('--apply', action='store_true', 
                       help='Apply changes (default is dry run)')
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        normalize_pxrf_data(db, dry_run=not args.apply)
    finally:
        db.close()

