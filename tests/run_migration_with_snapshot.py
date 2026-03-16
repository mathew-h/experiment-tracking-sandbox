#!/usr/bin/env python3
"""
Script to run data migrations with automatic snapshot creation and verification.

This script:
1. Creates a snapshot of the current database
2. Creates a temporary test copy
3. Runs the migration on the test copy
4. Compares before/after states
5. Provides option to apply to production

Usage:
    python tests/run_migration_with_snapshot.py establish_experiment_lineage_006
    python tests/run_migration_with_snapshot.py establish_experiment_lineage_006 --apply
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tests.snapshot import DatabaseSnapshot, get_experiment_lineage_info, print_lineage_report
from config import DATABASE_URL


def run_migration_with_snapshot(migration_name: str, apply: bool = False):
    """
    Run a data migration with snapshot protection.
    
    Args:
        migration_name: Name of the migration to run
        apply: If True, apply migration to production database
    """
    print("=" * 70)
    print("DATA MIGRATION WITH SNAPSHOT")
    print("=" * 70)
    print(f"Migration: {migration_name}")
    print(f"Mode: {'PRODUCTION' if apply else 'TEST'}")
    print("=" * 70)
    
    # Get database path from DATABASE_URL
    if not DATABASE_URL.startswith('sqlite:///'):
        print("❌ Error: This tool currently only supports SQLite databases")
        return False
    
    db_path = DATABASE_URL.replace('sqlite:///', '')
    
    if not os.path.exists(db_path):
        print(f"❌ Error: Database not found at {db_path}")
        return False
    
    print(f"\n📊 Source database: {db_path}")
    
    # Create snapshot utility
    snapshot = DatabaseSnapshot(db_path)
    
    try:
        # Step 1: Create snapshot
        print("\n" + "─" * 70)
        print("STEP 1: Creating snapshot of current database")
        print("─" * 70)
        snapshot_path = snapshot.create_snapshot(f"pre_{migration_name}")
        
        # Step 2: Get initial state
        print("\n" + "─" * 70)
        print("STEP 2: Analyzing current database state")
        print("─" * 70)
        
        initial_row_counts = snapshot.get_table_row_counts(db_path)
        print(f"\nTable row counts:")
        for table, count in sorted(initial_row_counts.items()):
            print(f"  {table:30} {count:6} rows")
        
        # Get lineage info before migration
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        
        print("\n" + "─" * 70)
        print("Current experiment lineage state:")
        lineage_before = get_experiment_lineage_info(session)
        print_lineage_report(lineage_before)
        session.close()
        
        # Step 3: Create temp copy for testing
        if not apply:
            print("\n" + "─" * 70)
            print("STEP 3: Creating temporary test database")
            print("─" * 70)
            temp_db_path, temp_url = snapshot.create_temp_copy()
            test_database_url = temp_url
        else:
            print("\n" + "─" * 70)
            print("STEP 3: Running on PRODUCTION database (--apply mode)")
            print("─" * 70)
            test_database_url = DATABASE_URL
            temp_db_path = db_path
        
        # Step 4: Run migration
        print("\n" + "─" * 70)
        print(f"STEP 4: Running migration on {'test copy' if not apply else 'PRODUCTION'}")
        print("─" * 70)
        
        # Import migration module
        migration_module_path = f"database.data_migrations.{migration_name}"
        try:
            migration_module = __import__(migration_module_path, fromlist=['run_migration', 'establish_experiment_lineage'])
            
            # Check if this is the lineage migration
            if hasattr(migration_module, 'establish_experiment_lineage'):
                # Temporarily override SessionLocal for test runs
                if not apply:
                    import database.data_migrations.establish_experiment_lineage_006 as lineage_mod
                    original_session = lineage_mod.SessionLocal
                    
                    # Create test session
                    test_engine = create_engine(test_database_url)
                    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
                    
                    class MockSessionLocal:
                        def __call__(self):
                            return TestSessionLocal()
                    
                    lineage_mod.SessionLocal = MockSessionLocal()
                    
                    try:
                        summary = migration_module.establish_experiment_lineage(dry_run=False)
                    finally:
                        lineage_mod.SessionLocal = original_session
                else:
                    summary = migration_module.establish_experiment_lineage(dry_run=False)
                
                print(f"\n✓ Migration completed")
                print(f"  Experiments scanned:     {summary['experiments_scanned']}")
                print(f"  Derivations found:       {summary['derivations_found']}")
                print(f"  Parents linked:          {summary['parents_linked']}")
                print(f"  Orphaned derivations:    {summary['orphaned_derivations']}")
                print(f"  Errors:                  {summary['errors']}")
            else:
                # For other migrations, just run them
                migration_module.run_migration()
            
        except ImportError as e:
            print(f"❌ Error: Could not import migration module: {e}")
            return False
        except Exception as e:
            print(f"❌ Error running migration: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Step 5: Verify changes
        print("\n" + "─" * 70)
        print("STEP 5: Verifying migration results")
        print("─" * 70)
        
        final_row_counts = snapshot.get_table_row_counts(temp_db_path)
        
        # Compare table counts
        print(f"\nTable row count changes:")
        all_tables = set(initial_row_counts.keys()) | set(final_row_counts.keys())
        has_changes = False
        
        for table in sorted(all_tables):
            before = initial_row_counts.get(table, 0)
            after = final_row_counts.get(table, 0)
            if before != after:
                delta = after - before
                print(f"  {table:30} {before:6} → {after:6} ({delta:+d})")
                has_changes = True
        
        if not has_changes:
            print("  No row count changes (migration updated existing rows)")
        
        # Get lineage info after migration
        test_engine = create_engine(test_database_url)
        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        test_session = TestSession()
        
        print("\n" + "─" * 70)
        print("Experiment lineage state after migration:")
        lineage_after = get_experiment_lineage_info(test_session)
        print_lineage_report(lineage_after)
        test_session.close()
        
        # Step 6: Summary
        print("\n" + "=" * 70)
        print("MIGRATION SUMMARY")
        print("=" * 70)
        
        if apply:
            print("✓ Migration applied to PRODUCTION database")
            print(f"✓ Snapshot saved at: {snapshot_path}")
            print(f"\nTo rollback, run:")
            print(f"  python tests/restore_snapshot.py {snapshot_path}")
        else:
            print("✓ Migration tested successfully on temporary copy")
            print(f"✓ Snapshot saved at: {snapshot_path}")
            print(f"\nTo apply to production, run:")
            print(f"  python tests/run_migration_with_snapshot.py {migration_name} --apply")
        
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cleanup temp files (only in test mode)
        if not apply:
            snapshot.cleanup()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    migration_name = sys.argv[1]
    apply = '--apply' in sys.argv
    
    # Confirm if applying to production
    if apply:
        print("\n⚠️  WARNING: You are about to apply this migration to the PRODUCTION database!")
        print("This operation will modify your data.")
        print("A snapshot will be created for rollback, but proceed with caution.")
        
        response = input("\nType 'YES' to confirm: ")
        if response != 'YES':
            print("Aborted.")
            sys.exit(0)
    
    success = run_migration_with_snapshot(migration_name, apply)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

