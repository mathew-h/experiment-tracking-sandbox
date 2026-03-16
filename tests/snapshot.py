"""
Database snapshot utility for testing data migrations.

This module provides tools to create snapshots of database state before running
migrations, allowing for easy verification and rollback during testing.
"""
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session


class DatabaseSnapshot:
    """
    Helper class for creating and managing database snapshots for migration testing.
    
    Supports both file-based and in-memory SQLite databases.
    """
    
    def __init__(self, source_db_path: str):
        """
        Initialize the snapshot utility.
        
        Args:
            source_db_path: Path to the source database file (e.g., 'experiments.db')
        """
        self.source_db_path = source_db_path
        self.snapshot_path: Optional[str] = None
        self.temp_dir: Optional[str] = None
        
    def create_snapshot(self, snapshot_name: Optional[str] = None) -> str:
        """
        Create a snapshot of the current database state.
        
        Args:
            snapshot_name: Optional name for the snapshot. If None, uses timestamp.
            
        Returns:
            Path to the snapshot file
        """
        if not os.path.exists(self.source_db_path):
            raise FileNotFoundError(f"Source database not found: {self.source_db_path}")
        
        # Generate snapshot filename
        if snapshot_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_name = f"snapshot_{timestamp}"
        
        # Create snapshots directory if it doesn't exist
        snapshots_dir = Path("tests/snapshots")
        snapshots_dir.mkdir(exist_ok=True)
        
        snapshot_path = snapshots_dir / f"{snapshot_name}.db"
        
        # Copy the database file
        shutil.copy2(self.source_db_path, snapshot_path)
        
        self.snapshot_path = str(snapshot_path)
        print(f"✓ Snapshot created: {self.snapshot_path}")
        
        return self.snapshot_path
    
    def create_temp_copy(self) -> tuple[str, str]:
        """
        Create a temporary copy of the database for testing.
        
        Returns:
            Tuple of (temp_db_path, temp_database_url)
        """
        if not os.path.exists(self.source_db_path):
            raise FileNotFoundError(f"Source database not found: {self.source_db_path}")
        
        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp(prefix="db_migration_test_")
        
        # Copy database to temp location
        temp_db_path = os.path.join(self.temp_dir, "test_migration.db")
        shutil.copy2(self.source_db_path, temp_db_path)
        
        temp_database_url = f"sqlite:///{temp_db_path}"
        
        print(f"✓ Temporary test database created: {temp_db_path}")
        
        return temp_db_path, temp_database_url
    
    def restore_snapshot(self, target_path: Optional[str] = None) -> None:
        """
        Restore database from snapshot.
        
        Args:
            target_path: Path to restore to. If None, restores to original source path.
        """
        if not self.snapshot_path or not os.path.exists(self.snapshot_path):
            raise FileNotFoundError("No snapshot available to restore")
        
        restore_target = target_path or self.source_db_path
        
        # Backup existing database before restore
        if os.path.exists(restore_target):
            backup_path = f"{restore_target}.backup"
            shutil.copy2(restore_target, backup_path)
            print(f"✓ Existing database backed up to: {backup_path}")
        
        # Restore from snapshot
        shutil.copy2(self.snapshot_path, restore_target)
        print(f"✓ Database restored from snapshot: {self.snapshot_path}")
    
    def cleanup(self) -> None:
        """Clean up temporary files and directories."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print(f"✓ Cleaned up temporary directory: {self.temp_dir}")
            self.temp_dir = None
    
    def get_table_row_counts(self, db_path: Optional[str] = None) -> Dict[str, int]:
        """
        Get row counts for all tables in the database.
        
        Args:
            db_path: Path to database. If None, uses source database.
            
        Returns:
            Dictionary mapping table names to row counts
        """
        target_db = db_path or self.source_db_path
        
        if not os.path.exists(target_db):
            raise FileNotFoundError(f"Database not found: {target_db}")
        
        conn = sqlite3.connect(target_db)
        cursor = conn.cursor()
        
        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        # Get row count for each table
        row_counts = {}
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            row_counts[table] = cursor.fetchone()[0]
        
        conn.close()
        
        return row_counts
    
    def compare_databases(self, db1_path: str, db2_path: str) -> Dict[str, Any]:
        """
        Compare two database snapshots.
        
        Args:
            db1_path: Path to first database
            db2_path: Path to second database
            
        Returns:
            Dictionary containing comparison results
        """
        counts1 = self.get_table_row_counts(db1_path)
        counts2 = self.get_table_row_counts(db2_path)
        
        all_tables = set(counts1.keys()) | set(counts2.keys())
        
        differences = {}
        for table in all_tables:
            count1 = counts1.get(table, 0)
            count2 = counts2.get(table, 0)
            
            if count1 != count2:
                differences[table] = {
                    'before': count1,
                    'after': count2,
                    'delta': count2 - count1
                }
        
        return {
            'tables_compared': len(all_tables),
            'differences': differences,
            'identical': len(differences) == 0
        }


def get_experiment_lineage_info(db_session: Session) -> Dict[str, Any]:
    """
    Extract lineage information from experiments for verification.
    
    Args:
        db_session: Database session
        
    Returns:
        Dictionary containing lineage statistics and details
    """
    from database.models import Experiment
    
    all_experiments = db_session.query(Experiment).all()
    
    derivations = []
    base_experiments = []
    orphaned = []
    linked = []
    
    for exp in all_experiments:
        is_self_referential = exp.base_experiment_id == exp.experiment_id
        has_base_reference = bool(exp.base_experiment_id)

        if has_base_reference and not is_self_referential:
            # This is a derivation or treatment variant tied to a base experiment
            derivations.append({
                'experiment_id': exp.experiment_id,
                'base_experiment_id': exp.base_experiment_id,
                'parent_experiment_fk': exp.parent_experiment_fk,
                'has_parent': exp.parent_experiment_fk is not None
            })

            if exp.parent_experiment_fk:
                linked.append(exp.experiment_id)
            else:
                orphaned.append(exp.experiment_id)
        else:
            # This is a base experiment (self-referential lineage or no base reference)
            base_experiments.append(exp.experiment_id)
    
    return {
        'total_experiments': len(all_experiments),
        'base_experiments': len(base_experiments),
        'derivations': len(derivations),
        'linked_derivations': len(linked),
        'orphaned_derivations': len(orphaned),
        'derivation_details': derivations,
        'base_experiment_ids': base_experiments,
        'linked_experiment_ids': linked,
        'orphaned_experiment_ids': orphaned
    }


def print_lineage_report(lineage_info: Dict[str, Any]) -> None:
    """
    Print a formatted report of experiment lineage information.
    
    Args:
        lineage_info: Dictionary from get_experiment_lineage_info()
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT LINEAGE REPORT")
    print("=" * 60)
    print(f"Total experiments:        {lineage_info['total_experiments']}")
    print(f"Base experiments:         {lineage_info['base_experiments']}")
    print(f"Derivations:              {lineage_info['derivations']}")
    print(f"  - Linked to parent:     {lineage_info['linked_derivations']}")
    print(f"  - Orphaned:             {lineage_info['orphaned_derivations']}")
    print("=" * 60)
    
    if lineage_info['orphaned_experiment_ids']:
        print("\nOrphaned derivations:")
        for exp_id in lineage_info['orphaned_experiment_ids']:
            print(f"  - {exp_id}")
    
    if lineage_info['linked_experiment_ids']:
        print("\nLinked derivations:")
        for exp_id in lineage_info['linked_experiment_ids']:
            print(f"  - {exp_id}")

