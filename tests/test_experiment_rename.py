"""
Test suite for experiment renaming via bulk upload with old_experiment_id column.

This test verifies the behavior of renaming experiments, including:
1. Simple renames
2. Chain renames (where new ID overlaps with another old ID)
3. Order-dependent scenarios
4. Lineage field updates after rename
5. Preservation of results, notes, and conditions
"""

import pytest
import pandas as pd
import io
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import (
    Base, Experiment, ExperimentNotes, ModificationsLog,
    ExperimentalResults, ScalarResults, ExperimentalConditions,
    ExperimentStatus
)
from backend.services.bulk_uploads.new_experiments import NewExperimentsUploadService
from database.lineage_utils import parse_experiment_id


@pytest.fixture
def db_session():
    """Create an in-memory test database session."""
    # Create in-memory SQLite database for testing
    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool
    )
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    # Create session
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    
    yield db
    
    # Cleanup
    db.close()
    Base.metadata.drop_all(engine)


def create_test_experiment(db: Session, exp_id: str, exp_number: int):
    """Helper to create a test experiment."""
    experiment = Experiment(
        experiment_number=exp_number,
        experiment_id=exp_id,
        researcher="MH",
        status=ExperimentStatus.ONGOING
    )
    db.add(experiment)
    db.flush()
    return experiment


def create_excel_with_renames(data):
    """Helper to create Excel file with experiments sheet."""
    df_exp = pd.DataFrame(data)
    
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df_exp.to_excel(writer, index=False, sheet_name='experiments')
    buf.seek(0)
    return buf.read()


class TestSimpleRename:
    """Test simple rename scenarios."""
    
    def test_basic_rename(self, db_session):
        """Test renaming a single experiment."""
        # Setup: Create experiment with old ID
        exp = create_test_experiment(db_session, "HPHT_MH_001", 1)
        exp_id = exp.id
        db_session.commit()
        
        # Action: Rename via bulk upload
        data = [{
            'experiment_id': 'HPHT_MH_001_Desorption',
            'old_experiment_id': 'HPHT_MH_001',
            'overwrite': True,
            'status': 'ONGOING'
        }]
        excel_bytes = create_excel_with_renames(data)
        
        created, updated, skipped, errors, warnings, info = \
            NewExperimentsUploadService.bulk_upsert_from_excel(db_session, excel_bytes)
        
        # Assert: No errors, experiment renamed
        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert updated == 1
        assert created == 0
        
        # Expire all cached objects to force fresh queries
        db_session.expire_all()
        
        # Verify rename happened
        renamed_exp = db_session.query(Experiment).filter(
            Experiment.id == exp_id
        ).first()
        assert renamed_exp is not None
        assert renamed_exp.experiment_id == 'HPHT_MH_001_Desorption'
        
        # Verify old ID doesn't exist
        old_exp = db_session.query(Experiment).filter(
            Experiment.experiment_id == 'HPHT_MH_001'
        ).first()
        assert old_exp is None
    
    def test_rename_updates_lineage(self, db_session):
        """Test that lineage fields are recalculated after rename."""
        # Setup: Create sequential experiment
        base = create_test_experiment(db_session, "HPHT_MH_036", 1)
        seq = create_test_experiment(db_session, "HPHT_MH_036-2", 2)
        seq.base_experiment_id = "HPHT_MH_036"
        seq.parent_experiment_fk = base.id
        db_session.commit()
        
        # Action: Rename sequential to treatment
        data = [{
            'experiment_id': 'HPHT_MH_036_Desorption',
            'old_experiment_id': 'HPHT_MH_036-2',
            'overwrite': True,
            'status': 'ONGOING'
        }]
        excel_bytes = create_excel_with_renames(data)
        
        created, updated, skipped, errors, warnings, info = \
            NewExperimentsUploadService.bulk_upsert_from_excel(db_session, excel_bytes)
        
        # Assert: Lineage updated
        assert len(errors) == 0
        renamed = db_session.query(Experiment).filter(
            Experiment.id == seq.id
        ).first()
        
        assert renamed.experiment_id == 'HPHT_MH_036_Desorption'
        # Lineage should be recalculated: treatment variant of base
        base_id, deriv_num, treatment = parse_experiment_id(renamed.experiment_id)
        assert base_id == "HPHT_MH_036"
        assert deriv_num is None
        assert treatment == "Desorption"
        
        db_session.rollback()


class TestChainRenames:
    """Test scenarios where new IDs overlap with old IDs."""
    
    def test_chain_rename_correct_order(self, db_session):
        """
        Test chain rename in correct order:
        HPHT_MH_036-2 -> HPHT_MH_036_Desorption (frees up -2)
        HPHT_MH_036-5 -> HPHT_MH_036-2 (uses freed name)
        """
        # Setup
        exp1 = create_test_experiment(db_session, "HPHT_MH_036", 1)
        exp2 = create_test_experiment(db_session, "HPHT_MH_036-2", 2)
        exp3 = create_test_experiment(db_session, "HPHT_MH_036-5", 5)
        db_session.commit()
        
        # Action: Process in correct order (2 then 5)
        data = [
            {
                'experiment_id': 'HPHT_MH_036',
                'old_experiment_id': 'HPHT_MH_036',
                'overwrite': True,
                'status': 'ONGOING'
            },
            {
                'experiment_id': 'HPHT_MH_036_Desorption',
                'old_experiment_id': 'HPHT_MH_036-2',
                'overwrite': True,
                'status': 'ONGOING'
            },
            {
                'experiment_id': 'HPHT_MH_036-2',
                'old_experiment_id': 'HPHT_MH_036-5',
                'overwrite': True,
                'status': 'ONGOING'
            }
        ]
        excel_bytes = create_excel_with_renames(data)
        
        created, updated, skipped, errors, warnings, info = \
            NewExperimentsUploadService.bulk_upsert_from_excel(db_session, excel_bytes)
        
        # Assert: All renames successful
        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert updated == 3
        assert created == 0
        
        # Verify final state
        exp1_after = db_session.query(Experiment).filter(Experiment.id == exp1.id).first()
        exp2_after = db_session.query(Experiment).filter(Experiment.id == exp2.id).first()
        exp3_after = db_session.query(Experiment).filter(Experiment.id == exp3.id).first()
        
        assert exp1_after.experiment_id == "HPHT_MH_036"
        assert exp2_after.experiment_id == "HPHT_MH_036_Desorption"
        assert exp3_after.experiment_id == "HPHT_MH_036-2"
        
        # Verify no orphaned experiment IDs
        all_exp_ids = [e.experiment_id for e in db_session.query(Experiment).all()]
        assert "HPHT_MH_036-5" not in all_exp_ids  # Old ID should be gone
        
        db_session.rollback()
    
    def test_chain_rename_wrong_order(self, db_session):
        """
        Test chain rename in WRONG order to demonstrate the issue:
        HPHT_MH_036-5 -> HPHT_MH_036-2 (first)
        HPHT_MH_036-2 -> HPHT_MH_036_Desorption (tries to rename to existing name)
        
        This should produce a UNIQUE constraint error.
        """
        # Setup
        exp1 = create_test_experiment(db_session, "HPHT_MH_036", 1)
        exp2 = create_test_experiment(db_session, "HPHT_MH_036-2", 2)
        exp3 = create_test_experiment(db_session, "HPHT_MH_036-5", 5)
        db_session.commit()
        
        # Action: Process in WRONG order (5 then 2)
        data = [
            {
                'experiment_id': 'HPHT_MH_036-2',
                'old_experiment_id': 'HPHT_MH_036-5',
                'overwrite': True,
                'status': 'ONGOING'
            },
            {
                'experiment_id': 'HPHT_MH_036_Desorption',
                'old_experiment_id': 'HPHT_MH_036-2',
                'overwrite': True,
                'status': 'ONGOING'
            }
        ]
        excel_bytes = create_excel_with_renames(data)
        
        created, updated, skipped, errors, warnings, info = \
            NewExperimentsUploadService.bulk_upsert_from_excel(db_session, excel_bytes)
        
        # Assert: Wrong order produces helpful error message
        print(f"\nWrong order results (expected chain rename conflict):")
        print(f"  Created: {created}, Updated: {updated}, Skipped: {skipped}")
        print(f"  Errors: {errors}")
        print(f"  Warnings: {warnings}")
        print(f"  Info: {info}")
        
        # Verify that chain rename conflict was detected with helpful message
        chain_rename_warnings = [w for w in warnings if 'CHAIN RENAME' in str(w)]
        assert len(chain_rename_warnings) > 0, \
            "Expected helpful CHAIN RENAME CONFLICT warning when renaming in wrong order"
        
        # Verify the warning mentions ordering
        assert any('AWAY from' in str(w) and 'INTO them' in str(w) for w in warnings), \
            "Expected warning to mention correct ordering strategy"
        
        # Verify the warning references documentation
        assert any('EXPERIMENT_RENAME_GUIDE' in str(w) for w in warnings), \
            "Expected warning to reference documentation"
        
        # Verify behavior: conflict row skipped, but valid rows still processed
        # Row 2 (rename -5 to -2) should be SKIPPED due to conflict
        # Row 3 (rename original -2 to _Desorption) should SUCCEED
        assert updated == 1, "One valid rename should succeed even when another has a conflict"
        
        # Verify that the second rename (valid one) succeeded
        exp2_id = exp2.id
        db_session.expire_all()
        exp2_after = db_session.query(Experiment).filter(Experiment.id == exp2_id).first()
        assert exp2_after.experiment_id == 'HPHT_MH_036_Desorption', \
            "The original HPHT_MH_036-2 should have been renamed to _Desorption"
        
        # Verify the first rename (conflicted one) did NOT happen
        exp3_id = exp3.id
        exp3_after = db_session.query(Experiment).filter(Experiment.id == exp3_id).first()
        assert exp3_after.experiment_id == 'HPHT_MH_036-5', \
            "HPHT_MH_036-5 should remain unchanged due to conflict"
        
        print("\n✓ Chain rename conflict correctly detected with helpful error message!")
        print("✓ Conflicted row skipped, valid rows still processed!")


class TestRenamePreservesRelationships:
    """Test that renames preserve all relationships."""
    
    def test_rename_preserves_results(self, db_session):
        """Test that results remain linked after rename."""
        # Setup: Experiment with results
        exp = create_test_experiment(db_session, "HPHT_MH_001", 1)
        
        result = ExperimentalResults(
            experiment_fk=exp.id,
            time_post_reaction_days=1.0,
            description="Test result"
        )
        db_session.add(result)
        db_session.flush()  # Flush to get result.id before using it
        
        scalar = ScalarResults(
            result_id=result.id,
            final_ph=7.0
        )
        db_session.add(scalar)
        db_session.commit()
        
        result_id = result.id
        exp_id = exp.id
        
        # Action: Rename
        data = [{
            'experiment_id': 'HPHT_MH_001_Renamed',
            'old_experiment_id': 'HPHT_MH_001',
            'overwrite': True,
            'status': 'ONGOING'
        }]
        excel_bytes = create_excel_with_renames(data)
        
        created, updated, skipped, errors, warnings, info = \
            NewExperimentsUploadService.bulk_upsert_from_excel(db_session, excel_bytes)
        
        # Assert: Results still linked
        assert len(errors) == 0
        
        # Expire cached objects to get fresh data
        db_session.expire_all()
        
        result_after = db_session.query(ExperimentalResults).filter(
            ExperimentalResults.id == result_id
        ).first()
        
        assert result_after is not None
        assert result_after.experiment_fk == exp_id  # FK unchanged
        assert result_after.experiment.experiment_id == 'HPHT_MH_001_Renamed'
    
    def test_rename_updates_notes(self, db_session):
        """Test that denormalized experiment_id in notes is updated."""
        # Setup: Experiment with notes
        exp = create_test_experiment(db_session, "HPHT_MH_001", 1)
        
        note = ExperimentNotes(
            experiment_fk=exp.id,
            experiment_id=exp.experiment_id,
            note_text="Original note"
        )
        db_session.add(note)
        db_session.commit()
        
        note_id = note.id
        exp_id = exp.id
        
        # Action: Rename
        data = [{
            'experiment_id': 'HPHT_MH_001_Renamed',
            'old_experiment_id': 'HPHT_MH_001',
            'overwrite': True,
            'status': 'ONGOING'
        }]
        excel_bytes = create_excel_with_renames(data)
        
        created, updated, skipped, errors, warnings, info = \
            NewExperimentsUploadService.bulk_upsert_from_excel(db_session, excel_bytes)
        
        # Assert: Note's denormalized experiment_id updated
        assert len(errors) == 0
        
        # Expire cached objects
        db_session.expire_all()
        
        note_after = db_session.query(ExperimentNotes).filter(
            ExperimentNotes.id == note_id
        ).first()
        
        assert note_after.experiment_id == 'HPHT_MH_001_Renamed'


class TestRenameWithConditionsAndAdditives:
    """Test that conditions and additives sheets work with renamed experiments."""
    
    def test_rename_with_conditions_sheet(self, db_session):
        """Test that conditions sheet can find renamed experiments using template-style column names."""
        # Setup: Create experiment
        exp = create_test_experiment(db_session, "HPHT_MH_001", 1)
        db_session.commit()
        
        # Action: Rename in experiments sheet AND add conditions
        # Use template-style column names with parenthetical hints
        experiments_df = pd.DataFrame([{
            'experiment_id* (TYPE_INITIALS_INDEX)': 'HPHT_MH_001_Desorption',
            'old_experiment_id (optional, for renames)': 'HPHT_MH_001',
            'overwrite': True,
            'status': 'ONGOING'
        }])
        
        conditions_df = pd.DataFrame([{
            'experiment_id*': 'HPHT_MH_001_Desorption',  # Use NEW ID in conditions sheet
            'rock_mass': 50.0,
            'water_volume': 500.0
        }])
        
        # Debug: verify DataFrame structure
        print(f"\nExperiments DataFrame columns: {list(experiments_df.columns)}")
        print(f"Conditions DataFrame columns: {list(conditions_df.columns)}")
        print(f"Conditions DataFrame values:\n{conditions_df}")
        
        # Create multi-sheet Excel
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            experiments_df.to_excel(writer, index=False, sheet_name='experiments')
            conditions_df.to_excel(writer, index=False, sheet_name='conditions')
        buf.seek(0)
        
        created, updated, skipped, errors, warnings, info = \
            NewExperimentsUploadService.bulk_upsert_from_excel(db_session, buf.read())
        
        # Assert: No errors - experiment renamed AND conditions added
        print(f"\nRename with conditions results:")
        print(f"  Created: {created}, Updated: {updated}")
        print(f"  Errors: {errors}")
        print(f"  Warnings: {warnings}")
        print(f"  Info: {info}")
        
        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(warnings) == 0, f"Unexpected warnings: {warnings}"
        assert updated == 1, "Experiment should be updated"
        
        # Verify conditions were added
        db_session.expire_all()
        exp_after = db_session.query(Experiment).filter(Experiment.id == exp.id).first()
        assert exp_after.experiment_id == 'HPHT_MH_001_Desorption'
        assert exp_after.conditions is not None, "Conditions should exist"
        
        # Debug: print actual values
        print(f"\n  Conditions rock_mass_g: {exp_after.conditions.rock_mass_g}")
        print(f"  Conditions water_volume_mL: {exp_after.conditions.water_volume_mL}")
        
        assert exp_after.conditions.rock_mass_g == 50.0, \
            f"Expected rock_mass_g=50.0, got {exp_after.conditions.rock_mass_g}"
        assert exp_after.conditions.water_volume_mL == 500.0, \
            f"Expected water_volume_mL=500.0, got {exp_after.conditions.water_volume_mL}"


class TestRenameEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_rename_without_overwrite_flag(self, db_session):
        """Test that rename requires overwrite=True."""
        exp = create_test_experiment(db_session, "HPHT_MH_001", 1)
        db_session.commit()
        
        # Action: Try rename without overwrite
        data = [{
            'experiment_id': 'HPHT_MH_001_Renamed',
            'old_experiment_id': 'HPHT_MH_001',
            'overwrite': False,  # Should fail
            'status': 'ONGOING'
        }]
        excel_bytes = create_excel_with_renames(data)
        
        created, updated, skipped, errors, warnings, info = \
            NewExperimentsUploadService.bulk_upsert_from_excel(db_session, excel_bytes)
        
        # Assert: No rename happened
        exp_after = db_session.query(Experiment).filter(Experiment.id == exp.id).first()
        assert exp_after.experiment_id == "HPHT_MH_001"  # Unchanged
        
        db_session.rollback()
    
    def test_old_experiment_id_not_found(self, db_session):
        """Test error when old_experiment_id doesn't exist."""
        # Action: Try to rename non-existent experiment
        data = [{
            'experiment_id': 'HPHT_MH_999_Renamed',
            'old_experiment_id': 'HPHT_MH_999',  # Doesn't exist
            'overwrite': True,
            'status': 'ONGOING'
        }]
        excel_bytes = create_excel_with_renames(data)
        
        created, updated, skipped, errors, warnings, info = \
            NewExperimentsUploadService.bulk_upsert_from_excel(db_session, excel_bytes)
        
        # Assert: Warning about not found
        assert any('HPHT_MH_999' in w and 'not found' in w for w in warnings)
        assert updated == 0
        
        db_session.rollback()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])

