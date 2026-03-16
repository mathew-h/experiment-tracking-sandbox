#!/usr/bin/env python3
"""
Script to restore a database from a snapshot.

Usage:
    python tests/restore_snapshot.py <snapshot_path>
    python tests/restore_snapshot.py tests/snapshots/pre_establish_experiment_lineage_006.db
"""
import sys
import os
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import DATABASE_URL


def restore_from_snapshot(snapshot_path: str):
    """
    Restore database from a snapshot.
    
    Args:
        snapshot_path: Path to the snapshot file
    """
    print("=" * 70)
    print("RESTORE DATABASE FROM SNAPSHOT")
    print("=" * 70)
    
    # Get database path from DATABASE_URL
    if not DATABASE_URL.startswith('sqlite:///'):
        print("❌ Error: This tool currently only supports SQLite databases")
        return False
    
    db_path = DATABASE_URL.replace('sqlite:///', '')
    
    if not os.path.exists(snapshot_path):
        print(f"❌ Error: Snapshot not found at {snapshot_path}")
        return False
    
    print(f"\n📊 Target database: {db_path}")
    print(f"📸 Snapshot source: {snapshot_path}")
    
    # Confirm restore
    print("\n⚠️  WARNING: This will overwrite the current database!")
    print("The current database will be backed up with a .pre-restore extension.")
    
    response = input("\nType 'YES' to confirm restore: ")
    if response != 'YES':
        print("Aborted.")
        return False
    
    try:
        # Backup current database
        if os.path.exists(db_path):
            backup_path = f"{db_path}.pre-restore"
            counter = 1
            while os.path.exists(backup_path):
                backup_path = f"{db_path}.pre-restore.{counter}"
                counter += 1
            
            print(f"\n✓ Backing up current database to: {backup_path}")
            shutil.copy2(db_path, backup_path)
        
        # Restore from snapshot
        print(f"✓ Restoring database from snapshot...")
        shutil.copy2(snapshot_path, db_path)
        
        print("\n" + "=" * 70)
        print("✓ DATABASE RESTORED SUCCESSFULLY")
        print("=" * 70)
        print(f"Restored from: {snapshot_path}")
        print(f"Current backup: {backup_path}")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error during restore: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print(__doc__)
        print("\nAvailable snapshots:")
        snapshot_dir = "tests/snapshots"
        if os.path.exists(snapshot_dir):
            snapshots = [f for f in os.listdir(snapshot_dir) if f.endswith('.db')]
            if snapshots:
                for snapshot in sorted(snapshots):
                    path = os.path.join(snapshot_dir, snapshot)
                    size = os.path.getsize(path) / 1024  # KB
                    print(f"  - {path} ({size:.1f} KB)")
            else:
                print("  (No snapshots found)")
        else:
            print("  (Snapshot directory does not exist)")
        
        sys.exit(1)
    
    snapshot_path = sys.argv[1]
    success = restore_from_snapshot(snapshot_path)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

