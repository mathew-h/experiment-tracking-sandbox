#!/usr/bin/env python3
"""
Quick test for ICP label parsing with dashes and underscores in experiment IDs
"""
import re

def extract_sample_info(label):
    """Test version of the extract_sample_info function"""
    try:
        # Pattern to find the last occurrence of _(Day|Time)Number_DilutionFactorx
        time_pattern = r'_(Day|Time)(\d+(?:\.\d+)?)_(\d+(?:\.\d+)?)x?$'
        time_match = re.search(time_pattern, label, re.IGNORECASE)
        
        if not time_match:
            raise ValueError(f"Label format not recognized: {label}")
        
        # Extract the experiment ID by removing the time pattern from the end
        experiment_id = label[:time_match.start()]
        time_unit = time_match.group(1).lower()
        time_value = float(time_match.group(2))
        dilution_factor = float(time_match.group(3))
        
        return {
            'experiment_id': experiment_id,
            'time_unit': time_unit,
            'time_value': time_value,
            'dilution_factor': dilution_factor,
            'success': True
        }
    except Exception as e:
        return {'error': str(e), 'success': False}

def test_label_parsing():
    """Test various experiment ID formats"""
    test_cases = [
        # Basic formats
        'Serum_MH_011_Day5_5x',
        'Serum-MH-025_Time3_10x',
        
        # Complex IDs with multiple separators
        'Test_Sample_A_B_Day1_2x',
        'Complex-ID_With_Many_Parts_Day7_3x',
        'Project_ABC_123_XYZ_Time2.5_1.5x',
        
        # Simple formats
        'Simple_Day2_1x',
        'Basic-Test_Time1_10x',
        
        # Edge cases
        'A_B_C_D_E_F_Day0_1x',
        'Single_Day10_25x',
        
        # Should fail
        'InvalidFormat',
        'Missing_Time_5x',
        'No_Dilution_Day5'
    ]
    
    print("Testing ICP Label Parsing with Dashes and Underscores\n")
    print(f"{'Label':<40} {'Status':<10} {'Experiment ID':<25} {'Time':<8} {'Dilution'}")
    print("-" * 90)
    
    for label in test_cases:
        result = extract_sample_info(label)
        if result['success']:
            status = "✓ PASS"
            exp_id = result['experiment_id']
            time_val = f"{result['time_value']}"
            dilution = f"{result['dilution_factor']}x"
        else:
            status = "✗ FAIL"
            exp_id = result['error'][:20] + "..." if len(result['error']) > 20 else result['error']
            time_val = "-"
            dilution = "-"
        
        print(f"{label:<40} {status:<10} {exp_id:<25} {time_val:<8} {dilution}")

if __name__ == "__main__":
    test_label_parsing()