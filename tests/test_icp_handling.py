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
        """Test best line selection based on intensity."""
        # Create test data with multiple lines per element
        test_data = {
            'Label': ['Sample1'] * 4,
            'Element Label': ['Fe 238.204', 'Fe 259.940', 'Mg 285.213', 'Mg 202.582'],
            'Concentration': [10.0, 8.0, 5.0, 4.8],
            'Intensity': [1500, 1200, 800, 750],  # Fe 238.204 and Mg 285.213 have higher intensity
            'Corrected_Concentration': [50.0, 40.0, 25.0, 24.0]
        }
        df = pd.DataFrame(test_data)
        
        best_lines = ICPService.select_best_lines(df)
        
        # Should select 2 rows (best line for each element)
        assert len(best_lines) == 2
        
        # Check that highest intensity lines were selected
        fe_row = best_lines[best_lines['Element Label'].str.startswith('Fe')].iloc[0]
        mg_row = best_lines[best_lines['Element Label'].str.startswith('Mg')].iloc[0]
        
        assert fe_row['Element Label'] == 'Fe 238.204'  # Higher intensity Fe line
        assert mg_row['Element Label'] == 'Mg 285.213'  # Higher intensity Mg line


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
