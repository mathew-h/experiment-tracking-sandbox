"""
Tests for ICP bulk upload handling, focusing on duplicate detection,
unique result tracking improvements, and edge cases.
"""

import pytest
import pandas as pd
from io import StringIO
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, Experiment, ExperimentalResults, ICPResults, ScalarResults
from backend.services.icp_service import ICPService
from backend.services.scalar_results_service import ScalarResultsService
from datetime import datetime


# Test database setup
@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    # SQLite does not support JSONB; swap to JSON before creating tables.
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    
    db = SessionLocal()
    
    # Create test experiment
    test_experiment = Experiment(
        experiment_id="Test_MH_001",
        experiment_number=1,
        researcher="Test Researcher",
        date=datetime.now(),
        status="ONGOING"
    )
    db.add(test_experiment)
    db.commit()
    
    yield db
    
    db.close()


@pytest.fixture
def sample_icp_csv_content():
    """Sample ICP CSV content for testing."""
    csv_content = """Header Row 1
Header Row 2
Label,Element Label,Concentration,Intensity,Type
Test_MH_001_Day3_10x,Fe 238.204,12.5,1500,SAMP
Test_MH_001_Day3_10x,Mg 285.213,4.2,800,SAMP
Test_MH_001_Day3_10x,Ni 231.604,2.1,600,SAMP
Test_MH_001_Day5_10x,Fe 238.204,15.8,1800,SAMP
Test_MH_001_Day5_10x,Mg 285.213,3.9,750,SAMP
Standard 1,Fe 238.204,100.0,5000,STD
Blank,Fe 238.204,0.1,50,BLK
"""
    return csv_content.encode('utf-8')


@pytest.fixture
def duplicate_icp_csv_content():
    """ICP CSV with same experiment and time point for duplicate testing."""
    csv_content = """Header Row 1
Header Row 2
Label,Element Label,Concentration,Intensity,Type
Test_MH_001_Day3_5x,Fe 238.204,6.25,1200,SAMP
Test_MH_001_Day3_5x,Mg 285.213,2.1,400,SAMP
Test_MH_001_Day3_5x,Cu 324.754,1.5,300,SAMP
"""
    return csv_content.encode('utf-8')


class TestICPServiceBasicFunctionality:
    """Test basic ICP service functionality."""
    
    def test_parse_csv_file(self, sample_icp_csv_content):
        """Test CSV file parsing with header skipping."""
        df = ICPService.parse_csv_file(sample_icp_csv_content)
        
        assert not df.empty
        assert 'Label' in df.columns
        assert 'Element Label' in df.columns
        assert 'Concentration' in df.columns
        assert 'Intensity' in df.columns
        
        # Should skip first 2 header rows
        assert len(df) == 7  # 7 data rows after headers
        
    def test_extract_sample_info_valid_labels(self):
        """Test sample info extraction from valid labels."""
        # Test various valid label formats
        test_cases = [
            ("Test_MH_001_Day3_10x", {"experiment_id": "Test_MH_001", "time_post_reaction": 3.0, "dilution_factor": 10.0}),
            ("Serum-MH-025_Time5_5x", {"experiment_id": "Serum-MH-025", "time_post_reaction": 5.0, "dilution_factor": 5.0}),
            ("Complex_Sample_ID_Day1_2x", {"experiment_id": "Complex_Sample_ID", "time_post_reaction": 1.0, "dilution_factor": 2.0}),
            ("HPHT_MH_004_Day7.5_15x", {"experiment_id": "HPHT_MH_004", "time_post_reaction": 7.5, "dilution_factor": 15.0}),
        ]
        
        for label, expected in test_cases:
            result = ICPService.extract_sample_info(label)
            assert result == expected, f"Failed for label: {label}"
    
    def test_extract_sample_info_invalid_labels(self):
        """Test sample info extraction returns None for invalid labels."""
        invalid_labels = [
            "Standard 1",
            "Blank",
            "QC Sample",
            "Control",
            "Standard_1",
            "Random Text",
            "",
        ]
        
        for label in invalid_labels:
            result = ICPService.extract_sample_info(label)
            assert result is None, f"Should return None for label: {label}"
    
    def test_apply_dilution_correction(self):
        """Test dilution factor application."""
        # Create test DataFrame
        test_data = {
            'Label': ['Sample1', 'Sample1'],
            'Element Label': ['Fe 238.204', 'Mg 285.213'],
            'Concentration': [10.0, 5.0],
            'Intensity': [1000, 500]
        }
        df = pd.DataFrame(test_data)
        
        # Apply 5x dilution correction
        corrected_df = ICPService.apply_dilution_correction(df, 5.0)
        
        assert 'Corrected_Concentration' in corrected_df.columns
        assert corrected_df['Corrected_Concentration'].iloc[0] == 50.0  # 10.0 * 5.0
        assert corrected_df['Corrected_Concentration'].iloc[1] == 25.0  # 5.0 * 5.0
    
    def test_select_best_lines(self):
        """Best line selection groups by element symbol and picks highest calibrated intensity."""
        test_data = {
            'Label': ['Sample1'] * 4,
            'Element Label': ['Fe 238.204', 'Fe 259.940', 'Mg 285.213', 'Mg 202.582'],
            'Concentration': [10.0, 8.0, 5.0, 4.8],
            'Intensity': [1500, 1200, 800, 750],
            'Corrected_Concentration': [50.0, 40.0, 25.0, 24.0],
        }
        df = pd.DataFrame(test_data)

        best_lines, warnings = ICPService.select_best_lines(df)

        assert len(warnings) == 0
        assert len(best_lines) == 2  # one row per element symbol

        fe_row = best_lines[best_lines['Element Label'].str.startswith('Fe')].iloc[0]
        mg_row = best_lines[best_lines['Element Label'].str.startswith('Mg')].iloc[0]

        assert fe_row['Element Label'] == 'Fe 238.204'   # higher intensity Fe line
        assert mg_row['Element Label'] == 'Mg 285.213'   # higher intensity Mg line


class TestICPServiceProcessing:
    """Test ICP data processing workflows."""
    
    def test_process_icp_dataframe_success(self, sample_icp_csv_content):
        """Test successful ICP DataFrame processing."""
        df = ICPService.parse_csv_file(sample_icp_csv_content)
        processed_data, errors = ICPService.process_icp_dataframe(df)
        
        # Should have 2 samples (Day3 and Day5 for Test_MH_001)
        assert len(processed_data) == 2
        
        # Should have warnings about skipped standards/blanks
        assert len(errors) == 2  # Standard 1 and Blank should be skipped
        assert any("Standard 1" in error for error in errors)
        assert any("Blank" in error for error in errors)
        
        # Check first sample data
        day3_sample = next((s for s in processed_data if s['time_post_reaction'] == 3.0), None)
        assert day3_sample is not None
        assert day3_sample['experiment_id'] == 'Test_MH_001'
        assert day3_sample['dilution_factor'] == 10.0
        assert 'fe' in day3_sample
        assert 'mg' in day3_sample
        assert 'ni' in day3_sample
    
    def test_parse_and_process_icp_file_complete_workflow(self, sample_icp_csv_content):
        """Test complete ICP file processing workflow."""
        processed_data, errors = ICPService.parse_and_process_icp_file(sample_icp_csv_content)
        
        assert len(processed_data) == 2
        assert len(errors) == 2  # Standards/blanks skipped
        
        # Validate data structure
        for sample in processed_data:
            assert 'experiment_id' in sample
            assert 'time_post_reaction' in sample
            assert 'dilution_factor' in sample
            assert 'raw_label' in sample


class TestICPDuplicateHandling:
    """Test ICP duplicate detection and handling."""
    
    def test_duplicate_icp_upload_same_time_point(self, test_db, sample_icp_csv_content, duplicate_icp_csv_content):
        """Test uploading ICP data twice for the same experiment and time point."""
        # First upload
        processed_data1, _ = ICPService.parse_and_process_icp_file(sample_icp_csv_content)
        results1, errors1 = ICPService.bulk_create_icp_results(test_db, processed_data1)
        
        assert len(results1) == 2  # Day3 and Day5
        assert len(errors1) == 0
        test_db.commit()
        
        # Second upload with same experiment and Day3 (different dilution factor)
        processed_data2, _ = ICPService.parse_and_process_icp_file(duplicate_icp_csv_content)
        results2, errors2 = ICPService.bulk_create_icp_results(test_db, processed_data2)
        
        # Should fail because ICP data already exists for Day3
        assert len(results2) == 0
        assert len(errors2) == 1
        assert "ICP data already exists" in errors2[0]
        assert "time 3.0" in errors2[0]
    
    def test_icp_upload_with_existing_scalar_data(self, test_db, sample_icp_csv_content):
        """Test uploading ICP data when scalar (NMR) data already exists for the same time point."""
        # First, create scalar results for Day3
        scalar_data = [{
            'experiment_id': 'Test_MH_001',
            'time_post_reaction': 3.0,
            'description': 'NMR Analysis',
            'gross_ammonium_concentration_mM': 15.5,
            'ammonium_quant_method': 'NMR',
            'final_ph': 7.2
        }]
        
        scalar_results, scalar_errors = ScalarResultsService.bulk_create_scalar_results(test_db, scalar_data)
        assert len(scalar_results) == 1
        assert len(scalar_errors) == 0
        test_db.commit()
        
        # Now upload ICP data for the same time point
        processed_data, _ = ICPService.parse_and_process_icp_file(sample_icp_csv_content)
        icp_results, icp_errors = ICPService.bulk_create_icp_results(test_db, processed_data)
        
        # Should succeed - both scalar and ICP can exist for same time point
        assert len(icp_results) == 2  # Day3 and Day5
        assert len(icp_errors) == 0
        test_db.commit()
        
        # Verify both data types exist for Day3
        experimental_result = test_db.query(ExperimentalResults).filter_by(
            experiment_id='Test_MH_001',
            time_post_reaction_days=3.0
        ).first()
        
        assert experimental_result is not None
        assert experimental_result.scalar_data is not None
        assert experimental_result.icp_data is not None
        
        # Check scalar data
        assert experimental_result.scalar_data.gross_ammonium_concentration_mM == 15.5
        assert experimental_result.scalar_data.ammonium_quant_method == 'NMR'
        
        # Check ICP data
        assert experimental_result.icp_data.fe is not None
        assert experimental_result.icp_data.dilution_factor == 10.0
    
    def test_scalar_upload_with_existing_icp_data(self, test_db, sample_icp_csv_content):
        """Test uploading scalar data when ICP data already exists for the same time point."""
        # First, upload ICP data
        processed_data, _ = ICPService.parse_and_process_icp_file(sample_icp_csv_content)
        icp_results, icp_errors = ICPService.bulk_create_icp_results(test_db, processed_data)
        
        assert len(icp_results) == 2
        assert len(icp_errors) == 0
        test_db.commit()
        
        # Now try to upload scalar data for the same time point
        scalar_data = [{
            'experiment_id': 'Test_MH_001',
            'time_post_reaction': 3.0,
            'description': 'NMR Analysis',
            'gross_ammonium_concentration_mM': 15.5,
            'ammonium_quant_method': 'NMR'
        }]
        
        scalar_results, scalar_errors = ScalarResultsService.bulk_create_scalar_results(test_db, scalar_data)
        
        # Should succeed - both data types can coexist
        assert len(scalar_results) == 1
        assert len(scalar_errors) == 0
        test_db.commit()
        
        # Verify both data types exist
        experimental_result = test_db.query(ExperimentalResults).filter_by(
            experiment_id='Test_MH_001',
            time_post_reaction_days=3.0
        ).first()
        
        assert experimental_result.scalar_data is not None
        assert experimental_result.icp_data is not None


class TestICPServiceEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_nonexistent_experiment(self, test_db):
        """Test uploading ICP data for non-existent experiment."""
        fake_data = [{
            'experiment_id': 'NonExistent_Exp_999',
            'time_post_reaction': 1.0,
            'dilution_factor': 5.0,
            'fe': 10.0,
            'mg': 5.0,
            'raw_label': 'NonExistent_Exp_999_Day1_5x'
        }]
        
        results, errors = ICPService.bulk_create_icp_results(test_db, fake_data)
        
        assert len(results) == 0
        assert len(errors) == 1
        assert "not found" in errors[0]
    
    def test_missing_required_fields(self, test_db):
        """Test ICP data with missing required fields."""
        incomplete_data = [
            {'time_post_reaction': 1.0, 'fe': 10.0},  # Missing experiment_id
            {'experiment_id': 'Test_MH_001', 'fe': 10.0},  # Missing time_post_reaction (now optional)
            {'experiment_id': 'Test_MH_001', 'time_post_reaction': 1.0}  # No elemental data
        ]
        
        results, errors = ICPService.bulk_create_icp_results(test_db, incomplete_data)
        
        assert len(results) == 0
        assert len(errors) == 2  # Only experiment_id missing and no elemental data should fail
        assert "Missing experiment_id" in errors[0]
        # time_post_reaction is now optional, so no error for missing time_post_reaction
    
    def test_empty_csv_file(self):
        """Test processing empty CSV file."""
        empty_csv = b"Header1\nHeader2\n"  # Only headers, no data
        
        processed_data, errors = ICPService.parse_and_process_icp_file(empty_csv)
        
        assert len(processed_data) == 0
        assert len(errors) > 0
    
    def test_csv_with_only_standards_and_blanks(self):
        """Test CSV file containing only standards and blanks (no samples)."""
        standards_only_csv = """Header Row 1
Header Row 2
Label,Element Label,Concentration,Intensity,Type
Standard 1,Fe 238.204,100.0,5000,STD
Standard 2,Fe 238.204,50.0,2500,STD
Blank,Fe 238.204,0.1,50,BLK
""".encode('utf-8')
        
        processed_data, errors = ICPService.parse_and_process_icp_file(standards_only_csv)
        
        assert len(processed_data) == 0
        assert len(errors) >= 3  # All samples skipped
        assert all("Skipped" in error for error in errors)
    
    def test_malformed_csv_structure(self):
        """Test handling of malformed CSV files."""
        malformed_csv = b"This is not a valid CSV file structure"
        
        processed_data, errors = ICPService.parse_and_process_icp_file(malformed_csv)
        
        assert len(processed_data) == 0
        assert len(errors) > 0
        assert "Error" in errors[0]


class TestICPModelMethods:
    """Test ICPResults model methods."""
    
    def test_icp_model_get_methods(self, test_db, sample_icp_csv_content):
        """Test ICPResults model get_element_concentration and get_all_detected_elements methods."""
        # Upload ICP data
        processed_data, _ = ICPService.parse_and_process_icp_file(sample_icp_csv_content)
        results, _ = ICPService.bulk_create_icp_results(test_db, processed_data)
        test_db.commit()
        
        # Get the ICP result
        icp_result = test_db.query(ICPResults).first()
        assert icp_result is not None
        
        # Test get_element_concentration method
        fe_concentration = icp_result.get_element_concentration('Fe')
        assert fe_concentration > 0
        
        # Test with element not present
        unknown_concentration = icp_result.get_element_concentration('Unknown')
        assert unknown_concentration == 0
        
        # Test get_all_detected_elements method
        all_elements = icp_result.get_all_detected_elements()
        assert isinstance(all_elements, dict)
        assert len(all_elements) > 0
        assert 'fe' in all_elements
        
        # Verify fixed columns are included
        if icp_result.fe is not None:
            assert 'fe' in all_elements
            assert all_elements['fe'] == icp_result.fe
    
    def test_icp_model_json_validation(self, test_db):
        """Test ICPResults model JSON field validation."""
        from database import ExperimentalResults
        
        # Create an experimental result first
        exp_result = ExperimentalResults(
            experiment_id='Test_MH_001',
            experiment_fk=1,
            time_post_reaction_days=1.0,
            description='Test'
        )
        test_db.add(exp_result)
        test_db.flush()
        
        # Test valid JSON data
        icp_result = ICPResults(
            result_id=exp_result.id,
            all_elements={'fe': 10.0, 'mg': 5.0},
            detection_limits={'fe': 0.1, 'mg': 0.05}
        )
        
        # Should not raise validation errors
        test_db.add(icp_result)
        test_db.flush()
        
        # Test invalid JSON data (should raise ValueError)
        with pytest.raises(ValueError):
            icp_result.all_elements = "invalid_json_string"
            icp_result.validate_json('all_elements', "invalid_json_string")


class TestUniqueResultTrackingImprovements:
    """Test the unique result tracking improvements architecture."""
    
    def test_multiple_data_types_same_time_point(self, test_db, sample_icp_csv_content):
        """Test that multiple analytical data types can exist for the same time point."""
        # Upload scalar data first
        scalar_data = [{
            'experiment_id': 'Test_MH_001',
            'time_post_reaction': 3.0,
            'description': 'Solution Chemistry Analysis',
            'gross_ammonium_concentration_mM': 12.5,
            'ammonium_quant_method': 'NMR',
            'final_ph': 7.1,
            'final_conductivity_mS_cm': 1200.0
        }]
        
        scalar_results, scalar_errors = ScalarResultsService.bulk_create_scalar_results(test_db, scalar_data)
        assert len(scalar_results) == 1
        test_db.commit()
        
        # Upload ICP data for the same time point
        processed_data, _ = ICPService.parse_and_process_icp_file(sample_icp_csv_content)
        icp_results, icp_errors = ICPService.bulk_create_icp_results(test_db, processed_data)
        assert len(icp_results) == 2  # Day3 and Day5
        test_db.commit()
        
        # Verify single ExperimentalResults record with both data types
        exp_result = test_db.query(ExperimentalResults).filter_by(
            experiment_id='Test_MH_001',
            time_post_reaction_days=3.0
        ).first()
        
        assert exp_result is not None
        assert exp_result.scalar_data is not None
        assert exp_result.icp_data is not None
        
        # Verify data integrity
        assert exp_result.scalar_data.gross_ammonium_concentration_mM == 12.5
        assert exp_result.icp_data.dilution_factor == 10.0
        assert exp_result.icp_data.fe is not None
    
    def test_experimental_results_reuse(self, test_db):
        """Test that ExperimentalResults records are properly reused."""
        # Create first data type
        scalar_data = [{
            'experiment_id': 'Test_MH_001',
            'time_post_reaction': 5.0,
            'description': 'First Analysis',
            'gross_ammonium_concentration_mM': 10.0
        }]
        
        ScalarResultsService.bulk_create_scalar_results(test_db, scalar_data)
        test_db.commit()
        
        # Count ExperimentalResults before second upload
        initial_count = test_db.query(ExperimentalResults).filter_by(
            experiment_id='Test_MH_001',
            time_post_reaction_days=5.0
        ).count()
        assert initial_count == 1
        
        # Add second data type to same time point
        icp_data = [{
            'experiment_id': 'Test_MH_001',
            'time_post_reaction': 5.0,
            'dilution_factor': 5.0,
            'fe': 15.0,
            'mg': 8.0,
            'raw_label': 'Test_MH_001_Day5_5x'
        }]
        
        ICPService.bulk_create_icp_results(test_db, icp_data)
        test_db.commit()
        
        # Should still be only 1 ExperimentalResults record
        final_count = test_db.query(ExperimentalResults).filter_by(
            experiment_id='Test_MH_001',
            time_post_reaction_days=5.0
        ).count()
        assert final_count == 1
        
        # Verify both data types are linked to the same ExperimentalResults
        exp_result = test_db.query(ExperimentalResults).filter_by(
            experiment_id='Test_MH_001',
            time_post_reaction_days=5.0
        ).first()
        
        assert exp_result.scalar_data is not None
        assert exp_result.icp_data is not None
        assert exp_result.scalar_data.result_id == exp_result.id
        assert exp_result.icp_data.result_id == exp_result.id


class TestICPZeroHandlingAndMerge:
    """Test non-numeric treated as 0, explicit 0 retained, and update preserves missing elements."""

    def test_non_numeric_concentration_stored_as_zero(self):
        """Sample with element concentration 'N/D' or empty string is stored as 0."""
        csv_with_nond = """Header Row 1
Header Row 2
Label,Element Label,Concentration,Intensity,Type
Test_MH_001_Day3_10x,Fe 238.204,N/D,1500,SAMP
Test_MH_001_Day3_10x,Mg 285.213,,800,SAMP
Test_MH_001_Day3_10x,Ni 231.604,2.1,600,SAMP
""".encode("utf-8")
        df = ICPService.parse_csv_file(csv_with_nond)
        processed_data, errors = ICPService.process_icp_dataframe(df)
        assert len(processed_data) == 1
        sample = processed_data[0]
        assert sample["fe"] == 0.0
        assert sample["mg"] == 0.0
        assert sample["ni"] == 21.0  # 2.1 * 10 dilution

    def test_explicit_zero_retained(self):
        """Sample with explicit 0 for an element retains 0 in the record."""
        csv_with_zero = """Header Row 1
Header Row 2
Label,Element Label,Concentration,Intensity,Type
Test_MH_001_Day3_10x,Fe 238.204,0,1500,SAMP
Test_MH_001_Day3_10x,Mg 285.213,4.2,800,SAMP
""".encode("utf-8")
        df = ICPService.parse_csv_file(csv_with_zero)
        processed_data, errors = ICPService.process_icp_dataframe(df)
        assert len(processed_data) == 1
        sample = processed_data[0]
        assert sample["fe"] == 0.0
        assert sample["mg"] == 42.0  # 4.2 * 10 dilution

    def test_update_preserves_elements_not_in_incoming_csv(
        self, test_db, sample_icp_csv_content
    ):
        """File A has Fe+Nd, File B has Fe only - Nd remains from File A after update."""
        csv_with_fe_nd = """Header Row 1
Header Row 2
Label,Element Label,Concentration,Intensity,Type
Test_MH_001_Day3_10x,Fe 238.204,12.5,1500,SAMP
Test_MH_001_Day3_10x,Nd 430.358,3.2,400,SAMP
""".encode("utf-8")
        csv_fe_only = """Header Row 1
Header Row 2
Label,Element Label,Concentration,Intensity,Type
Test_MH_001_Day3_5x,Fe 238.204,20.0,1800,SAMP
""".encode("utf-8")

        # Upload File A (Fe and Nd)
        processed_a, _ = ICPService.parse_and_process_icp_file(csv_with_fe_nd)
        results_a, _ = ICPService.bulk_create_icp_results(test_db, processed_a)
        assert len(results_a) == 1
        test_db.commit()

        # Upload File B (Fe only) - same experiment and time point
        processed_b, _ = ICPService.parse_and_process_icp_file(csv_fe_only)
        results_b, errors_b = ICPService.bulk_create_icp_results(test_db, processed_b)
        assert len(results_b) == 1
        test_db.commit()

        # Verify Nd preserved, Fe updated
        exp = test_db.query(Experiment).filter_by(experiment_id="Test_MH_001").first()
        er = test_db.query(ExperimentalResults).filter_by(
            experiment_fk=exp.id, time_post_reaction_days=3.0
        ).first()
        icp_result = er.icp_data
        assert icp_result is not None
        assert icp_result.nd == 32.0  # Preserved from File A (3.2 * 10 dilution)
        assert icp_result.fe == 100.0  # 20.0 * 5 dilution from File B


class TestICPOverwrite:
    """Test overwrite=True replaces existing ICP data instead of merging."""

    def test_overwrite_false_merges_elements(self, test_db):
        """Without overwrite, re-upload adds new elements but keeps old ones."""
        # First upload: fe + ni
        ICPService.bulk_create_icp_results(
            test_db,
            [{'experiment_id': 'Test_MH_001', 'time_post_reaction': 3.0,
              'description': 'Day 3', 'fe': 10.0, 'ni': 2.0}],
            overwrite=False,
        )
        # Second upload: fe only (no ni)
        ICPService.bulk_create_icp_results(
            test_db,
            [{'experiment_id': 'Test_MH_001', 'time_post_reaction': 3.0,
              'description': 'Day 3', 'fe': 99.0}],
            overwrite=False,
        )
        test_db.expire_all()
        experiment = test_db.query(Experiment).filter_by(experiment_id='Test_MH_001').first()
        result = test_db.query(ExperimentalResults).filter_by(
            experiment_fk=experiment.id,
        ).first()
        assert result.icp_data is not None
        assert result.icp_data.fe == 99.0       # updated
        assert result.icp_data.ni == 2.0        # preserved

    def test_overwrite_true_replaces_all_elements(self, test_db):
        """With overwrite=True, re-upload discards old elements and inserts fresh."""
        # First upload: fe + ni
        ICPService.bulk_create_icp_results(
            test_db,
            [{'experiment_id': 'Test_MH_001', 'time_post_reaction': 3.0,
              'description': 'Day 3', 'fe': 10.0, 'ni': 2.0}],
            overwrite=False,
        )
        # Capture the parent ExperimentalResults id before overwrite
        experiment = test_db.query(Experiment).filter_by(experiment_id='Test_MH_001').first()
        result_id_before = test_db.query(ExperimentalResults).filter_by(
            experiment_fk=experiment.id,
        ).first().id

        # Second upload with overwrite: fe only (ni should disappear)
        results, updated, errors = ICPService.bulk_create_icp_results(
            test_db,
            [{'experiment_id': 'Test_MH_001', 'time_post_reaction': 3.0,
              'description': 'Day 3', 'fe': 99.0}],
            overwrite=True,
        )
        assert errors == []
        assert updated == 0           # replaced rows count as "created", not "updated"
        test_db.expire_all()
        experiment = test_db.query(Experiment).filter_by(experiment_id='Test_MH_001').first()
        result = test_db.query(ExperimentalResults).filter_by(
            experiment_fk=experiment.id,
        ).first()
        assert result.id == result_id_before   # parent row was NOT replaced
        assert result.icp_data is not None
        assert result.icp_data.fe == 99.0
        assert result.icp_data.ni is None       # not preserved
        # all_elements JSON should also not contain ni from the first upload
        all_el = result.icp_data.all_elements or {}
        assert 'ni' not in all_el

    def test_overwrite_true_no_existing_data_creates_normally(self, test_db):
        """Overwrite with no prior ICP data behaves like a normal insert."""
        results, updated, errors = ICPService.bulk_create_icp_results(
            test_db,
            [{'experiment_id': 'Test_MH_001', 'time_post_reaction': 3.0,
              'description': 'Day 3', 'fe': 50.0}],
            overwrite=True,
        )
        assert errors == []
        assert updated == 0
        test_db.expire_all()
        experiment = test_db.query(Experiment).filter_by(experiment_id='Test_MH_001').first()
        result = test_db.query(ExperimentalResults).filter_by(
            experiment_fk=experiment.id,
        ).first()
        assert result.icp_data is not None
        assert result.icp_data.fe == 50.0


class TestICPRouterOverwrite:
    """Smoke-test that the router passes overwrite to the service."""

    def test_router_passes_overwrite_flag(self, monkeypatch):
        """upload_icp_oes forwards overwrite=True to bulk_create_icp_results."""
        from backend.auth.firebase_auth import FirebaseUser
        import sys
        from types import ModuleType

        # Stub frontend.config.variable_config before importing app
        if 'frontend.config.variable_config' not in sys.modules:
            stub = ModuleType('frontend.config.variable_config')
            sys.modules.setdefault('frontend', ModuleType('frontend'))
            sys.modules.setdefault('frontend.config', ModuleType('frontend.config'))
            sys.modules['frontend.config.variable_config'] = stub

        from fastapi.testclient import TestClient
        from backend.api.main import app

        # Patch auth dependency on the app before creating the client
        def mock_auth():
            return FirebaseUser(uid='test-uid', email='test@addisenergy.com')

        app.dependency_overrides[__import__('backend.auth.firebase_auth', fromlist=['verify_firebase_token']).verify_firebase_token] = mock_auth

        calls: list[bool] = []

        def fake_bulk_create(db, data, overwrite=False):
            calls.append(overwrite)
            return [], 0, []

        monkeypatch.setattr(
            'backend.services.icp_service.ICPService.bulk_create_icp_results',
            fake_bulk_create,
        )
        monkeypatch.setattr(
            'backend.services.icp_service.ICPService.parse_and_process_icp_file',
            lambda _: ([], []),
        )

        try:
            client = TestClient(app, raise_server_exceptions=False)
            csv_bytes = b'Label,Element Label,Concentration\n'
            response = client.post(
                '/api/bulk-uploads/icp-oes',
                data={'overwrite': 'true'},
                files={'file': ('test.csv', csv_bytes, 'text/csv')},
            )
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            assert len(calls) == 1, "bulk_create_icp_results was not called — overwrite flag not forwarded"
            assert calls[0] is True
        finally:
            app.dependency_overrides.clear()


class TestICPUncalHandling:
    """Tests for Uncal spectral-line fallback (issue #61)."""

    def test_uncal_highest_intensity_falls_back_to_next_line(self):
        """When the max-intensity line is Uncal, use the next-best calibrated line."""
        test_data = {
            'Label': ['Serum_MH_011_Day5_5x'] * 3,
            'Type': ['SAMP'] * 3,
            'Element Label': ['Fe 238.204', 'Fe 259.940', 'Fe 234.350'],
            'Concentration': ['Uncal', '50.0', '30.0'],
            'Intensity': [9999.0, 1500.0, 800.0],
        }
        df = pd.DataFrame(test_data)
        processed_data, errors = ICPService.process_icp_dataframe(df)

        assert len(processed_data) == 1
        # Fe 259.940 concentration 50.0 × 5 (dilution from label) = 250.0
        assert processed_data[0]['fe'] == 250.0
        # No Uncal warning — a valid fallback was found
        assert not any('Uncal' in e for e in errors)

    def test_all_spectral_lines_uncal_skips_element_and_warns(self):
        """When every spectral line for an element is Uncal, skip it and emit a warning."""
        test_data = {
            'Label': ['Serum_MH_011_Day5_5x'] * 3,
            'Type': ['SAMP'] * 3,
            'Element Label': ['Fe 238.204', 'Fe 259.940', 'Mg 285.213'],
            'Concentration': ['Uncal', 'UNCAL', '4.0'],
            'Intensity': [9999.0, 5000.0, 800.0],
        }
        df = pd.DataFrame(test_data)
        processed_data, errors = ICPService.process_icp_dataframe(df)

        assert len(processed_data) == 1
        sample = processed_data[0]
        assert 'fe' not in sample                  # all Fe lines Uncal — element absent
        assert sample['mg'] == 20.0                # 4.0 × 5 dilution
        assert any('Uncal' in e and 'fe' in e.lower() for e in errors)

    def test_select_best_lines_uncal_fallback_direct(self):
        """Unit: select_best_lines returns (df, []) when a valid fallback exists."""
        test_data = {
            'Label': ['S1', 'S1', 'S1'],
            'Element Label': ['Fe 238.204', 'Fe 259.940', 'Fe 234.350'],
            'Concentration': ['Uncal', '50.0', '30.0'],
            'Intensity': [9999.0, 1500.0, 800.0],
            'Corrected_Concentration': [float('nan'), 250.0, 150.0],  # pre-computed: not used by selection logic, row picked by Intensity + Uncal check
        }
        df = pd.DataFrame(test_data)

        best_lines, warnings = ICPService.select_best_lines(df)

        assert len(warnings) == 0
        assert len(best_lines) == 1
        assert best_lines.iloc[0]['Element Label'] == 'Fe 259.940'

    def test_select_best_lines_all_uncal_emits_warning_and_excludes_element(self):
        """Unit: select_best_lines warns and excludes elements where all lines are Uncal."""
        test_data = {
            'Label': ['S1', 'S1', 'S1'],
            'Element Label': ['Fe 238.204', 'Fe 259.940', 'Mg 285.213'],
            'Concentration': ['Uncal', 'uncal', '4.0'],
            'Intensity': [9999.0, 5000.0, 800.0],
            'Corrected_Concentration': [float('nan'), float('nan'), 20.0],
        }
        df = pd.DataFrame(test_data)

        best_lines, warnings = ICPService.select_best_lines(df)

        assert len(best_lines) == 1
        assert best_lines.iloc[0]['Element Label'] == 'Mg 285.213'
        assert len(warnings) == 1
        assert 'Uncal' in warnings[0]
        assert 'fe' in warnings[0].lower()
        assert "'S1'" in warnings[0]


class TestICPKNaStorage:
    """K and Na have model columns that must be populated via the bulk upload path."""

    def test_k_na_stored_in_fixed_columns_on_create(self, test_db):
        """A fresh ICP upload with K and Na must populate ICPResults.k and .na."""
        data = [{
            'experiment_id': 'Test_MH_001',
            'time_post_reaction': 20.0,
            'dilution_factor': 1.0,
            'k': 8.5,
            'na': 12.3,
            'fe': 50.0,
            'raw_label': 'Test_MH_001_Day20_1x',
        }]
        results, updated_count, errors = ICPService.bulk_create_icp_results(test_db, data)
        assert not errors, errors
        test_db.commit()

        icp = (
            test_db.query(ICPResults)
            .join(ExperimentalResults)
            .filter(ExperimentalResults.experiment_fk == results[0].experiment_fk)
            .filter(ExperimentalResults.time_post_reaction_bucket_days == 20.0)
            .first()
        )
        assert icp is not None, "ICPResults row not found"
        assert icp.k == 8.5,   f"Expected k=8.5, got {icp.k}"
        assert icp.na == 12.3, f"Expected na=12.3, got {icp.na}"
        assert icp.all_elements is not None
        assert icp.all_elements.get('k') == 8.5
        assert icp.all_elements.get('na') == 12.3

    def test_k_na_stored_in_fixed_columns_on_merge(self, test_db):
        """K and Na are populated on the UPDATE (merge) path too."""
        # File 1: Fe only
        first = [{
            'experiment_id': 'Test_MH_001',
            'time_post_reaction': 21.0,
            'dilution_factor': 1.0,
            'fe': 20.0,
            'raw_label': 'Test_MH_001_Day21_1x',
        }]
        results1, _, errors1 = ICPService.bulk_create_icp_results(test_db, first)
        assert not errors1, errors1
        test_db.commit()

        # File 2: same timepoint, K and Na only
        second = [{
            'experiment_id': 'Test_MH_001',
            'time_post_reaction': 21.0,
            'dilution_factor': 1.0,
            'k': 9.0,
            'na': 6.0,
            'raw_label': 'Test_MH_001_Day21_1x',
        }]
        results2, _, errors2 = ICPService.bulk_create_icp_results(test_db, second)
        assert not errors2, errors2
        test_db.commit()

        icp = (
            test_db.query(ICPResults)
            .join(ExperimentalResults)
            .filter(ExperimentalResults.experiment_fk == results1[0].experiment_fk)
            .filter(ExperimentalResults.time_post_reaction_bucket_days == 21.0)
            .first()
        )
        assert icp is not None, "ICPResults row not found after merge"
        assert icp.fe == 20.0,  "Fe from file 1 must be preserved"
        assert icp.k == 9.0,   f"Expected k=9.0, got {icp.k}"
        assert icp.na == 6.0,  f"Expected na=6.0, got {icp.na}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
