#!/usr/bin/env python3
"""
Standalone test file for ICP Service with corrected column references.
Tests the column handling and basic functionality.
"""

import pandas as pd
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from backend.services.icp_service import ICPService
    print("✅ ICPService imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

def test_column_requirements():
    """Test that the service expects the correct columns."""
    print("\n🧪 Testing Column Requirements")
    
    # Test data with correct columns from your screenshot
    test_data = {
        'Label': ['Serum_MH_011_Day5_5x', 'Serum_MH_011_Day5_5x', 'Serum_MH_025_Time3_10x'],
        'Type': ['SAMP', 'SAMP', 'SAMP'],
        'Element Label': ['Al 394.401', 'Fe 238.204', 'Mg 279.553'],
        'Concentration': [2.5, 125.0, 45.8],
        'Intensity': [1250.5, 8500.2, 2300.1]
    }
    
    df = pd.DataFrame(test_data)
    print(f"Test DataFrame columns: {list(df.columns)}")
    
    try:
        # Test select_best_lines function
        result = ICPService.select_best_lines(df)
        print("✅ select_best_lines() works with correct columns")
        print(f"   Returned {len(result)} rows")
    except Exception as e:
        print(f"❌ select_best_lines() failed: {e}")
    
    try:
        # Test process_icp_dataframe function
        processed_data, errors = ICPService.process_icp_dataframe(df)
        if errors:
            print(f"⚠️  Processing had errors: {errors}")
        else:
            print("✅ process_icp_dataframe() works with correct columns")
            print(f"   Processed {len(processed_data)} samples")
            if processed_data:
                sample = processed_data[0]
                print(f"   Sample keys: {list(sample.keys())}")
    except Exception as e:
        print(f"❌ process_icp_dataframe() failed: {e}")

def test_element_extraction():
    """Test that element symbols are correctly extracted from Element Label."""
    print("\n🧪 Testing Element Extraction")
    
    test_cases = [
        'Al 394.401',
        'Fe 238.204', 
        'Mg 279.553',
        'Cu 327.395',
        'Mo 202.032'
    ]
    
    for element_label in test_cases:
        element = element_label.split()[0]
        standardized = ICPService._standardize_element_name(element)
        print(f"   {element_label} -> {element} -> {standardized}")

def test_dilution_correction():
    """Test dilution correction with Concentration column."""
    print("\n🧪 Testing Dilution Correction")
    
    test_data = {
        'Label': ['Test_Sample_Day1_5x'],
        'Element Label': ['Fe 238.204'],
        'Concentration': [100.0],  # Raw concentration
        'Intensity': [5000.0]
    }
    
    df = pd.DataFrame(test_data)
    dilution_factor = 5.0
    
    try:
        corrected_df = ICPService.apply_dilution_correction(df, dilution_factor)
        if 'Corrected_Concentration' in corrected_df.columns:
            corrected_value = corrected_df['Corrected_Concentration'].iloc[0]
            expected_value = 100.0 * 5.0
            print(f"   Raw concentration: {df['Concentration'].iloc[0]}")
            print(f"   Dilution factor: {dilution_factor}")
            print(f"   Corrected concentration: {corrected_value}")
            print(f"   Expected: {expected_value}")
            if abs(corrected_value - expected_value) < 0.001:
                print("✅ Dilution correction works correctly")
            else:
                print("❌ Dilution correction calculation error")
        else:
            print("❌ Corrected_Concentration column not created")
    except Exception as e:
        print(f"❌ Dilution correction failed: {e}")

def test_label_parsing():
    """Test experiment ID, time, and dilution extraction from labels."""
    print("\n🧪 Testing Label Parsing")
    
    test_labels = [
        'Serum_MH_011_Day5_5x',
        'Serum-MH-025_Time3_10x',
        'Complex_Sample_ID_Day1_2x',
        'Test_Day7_1.5x'
    ]
    
    for label in test_labels:
        try:
            result = ICPService.extract_sample_info(label)
            print(f"   {label}")
            print(f"     -> Experiment ID: {result['experiment_id']}")
            print(f"     -> Time: {result['time_post_reaction']}")
            print(f"     -> Dilution: {result['dilution_factor']}")
        except Exception as e:
            print(f"   {label} -> ERROR: {e}")

def main():
    """Run all tests."""
    print("🔬 ICP Service Column Reference Test")
    print("=" * 50)
    
    print(f"\n📋 Expected Column Names:")
    print(f"   - Label: Sample identifiers")
    print(f"   - Element Label: Element with wavelength (e.g., 'Al 394.401')")
    print(f"   - Concentration: Raw concentration values")
    print(f"   - Intensity: Signal intensity for quality")
    
    test_column_requirements()
    test_element_extraction()
    test_dilution_correction()
    test_label_parsing()
    
    print("\n" + "=" * 50)
    print("🏁 Test completed!")

if __name__ == "__main__":
    main()