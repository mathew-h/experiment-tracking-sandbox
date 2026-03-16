"""
Diagnostic script to check experiment lineage data integrity.

This script will identify:
1. Experiments with incorrect base_experiment_id values
2. Experiments with mismatched parent relationships
3. Potential ID parsing issues
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import SessionLocal
from database.models import Experiment
from database.lineage_utils import parse_experiment_id

def check_lineage_integrity():
    """Check for lineage data integrity issues."""
    db = SessionLocal()
    
    issues = {
        "incorrect_base_id": [],
        "incorrect_self_reference": [],
        "orphaned_children": [],
        "unexpected_children": {}
    }
    
    try:
        experiments = db.query(Experiment).all()
        print(f"Checking {len(experiments)} experiments...\n")
        
        for exp in experiments:
            if not exp.experiment_id:
                continue
            
            # Parse the ID
            base_id, derivation_num, treatment_variant = parse_experiment_id(exp.experiment_id)
            
            # Check 1: For non-derivations, base_experiment_id should equal experiment_id
            if derivation_num is None and treatment_variant is None:
                expected_base = base_id or exp.experiment_id
                if exp.base_experiment_id != expected_base:
                    issues["incorrect_self_reference"].append({
                        "experiment_id": exp.experiment_id,
                        "current_base": exp.base_experiment_id,
                        "expected_base": expected_base
                    })
            
            # Check 2: For derivations, base_experiment_id should match the parsed base_id
            elif derivation_num is not None or treatment_variant is not None:
                if exp.base_experiment_id != base_id:
                    issues["incorrect_base_id"].append({
                        "experiment_id": exp.experiment_id,
                        "current_base": exp.base_experiment_id,
                        "expected_base": base_id,
                        "derivation_num": derivation_num,
                        "treatment_variant": treatment_variant
                    })
            
            # Check 3: Find unexpected children for each base experiment
            if exp.base_experiment_id and exp.base_experiment_id != exp.experiment_id:
                # This is a child, find its supposed base
                if exp.base_experiment_id not in issues["unexpected_children"]:
                    issues["unexpected_children"][exp.base_experiment_id] = []
                
                issues["unexpected_children"][exp.base_experiment_id].append({
                    "child_id": exp.experiment_id,
                    "parsed_base": base_id,
                    "stored_base": exp.base_experiment_id,
                    "matches": base_id == exp.base_experiment_id
                })
        
        # Print results
        print("=" * 80)
        print("LINEAGE INTEGRITY CHECK RESULTS")
        print("=" * 80)
        
        if issues["incorrect_self_reference"]:
            print(f"\n❌ Found {len(issues['incorrect_self_reference'])} experiments with incorrect self-references:")
            for issue in issues["incorrect_self_reference"][:10]:  # Show first 10
                print(f"   • {issue['experiment_id']}")
                print(f"     Current base_experiment_id: {issue['current_base']}")
                print(f"     Expected base_experiment_id: {issue['expected_base']}")
        
        if issues["incorrect_base_id"]:
            print(f"\n❌ Found {len(issues['incorrect_base_id'])} derivations with incorrect base_experiment_id:")
            for issue in issues["incorrect_base_id"][:10]:  # Show first 10
                print(f"   • {issue['experiment_id']}")
                print(f"     Current base_experiment_id: {issue['current_base']}")
                print(f"     Expected base_experiment_id: {issue['expected_base']}")
                if issue['treatment_variant']:
                    print(f"     Treatment variant: {issue['treatment_variant']}")
        
        # Check specific case: HPHT_JW_005
        print("\n" + "=" * 80)
        print("SPECIFIC CHECK: HPHT_JW_005")
        print("=" * 80)
        
        hpht_jw_005 = db.query(Experiment).filter(
            Experiment.experiment_id == "HPHT_JW_005"
        ).first()
        
        if hpht_jw_005:
            print(f"\n✓ Found HPHT_JW_005 (ID: {hpht_jw_005.id})")
            print(f"  base_experiment_id: {hpht_jw_005.base_experiment_id}")
            print(f"  parent_experiment_fk: {hpht_jw_005.parent_experiment_fk}")
            
            # Find all experiments claiming to be children
            children = db.query(Experiment).filter(
                Experiment.base_experiment_id == "HPHT_JW_005",
                Experiment.experiment_id != "HPHT_JW_005"
            ).all()
            
            print(f"\n  Experiments with base_experiment_id='HPHT_JW_005': {len(children)}")
            for child in children:
                parsed = parse_experiment_id(child.experiment_id)
                match = "✓" if parsed[0] == "HPHT_JW_005" else "❌"
                print(f"    {match} {child.experiment_id}")
                print(f"       Parsed as: base={parsed[0]}, seq={parsed[1]}, treatment={parsed[2]}")
        
        # Check OTHER_MH_001
        print("\n" + "=" * 80)
        print("SPECIFIC CHECK: OTHER_MH_001")
        print("=" * 80)
        
        other_mh_001 = db.query(Experiment).filter(
            Experiment.experiment_id == "OTHER_MH_001"
        ).first()
        
        if other_mh_001:
            print(f"\n✓ Found OTHER_MH_001 (ID: {other_mh_001.id})")
            print(f"  base_experiment_id: {other_mh_001.base_experiment_id}")
            print(f"  parent_experiment_fk: {other_mh_001.parent_experiment_fk}")
            parsed = parse_experiment_id("OTHER_MH_001")
            print(f"  Parsed as: base={parsed[0]}, seq={parsed[1]}, treatment={parsed[2]}")
        
        # Check CF-05-1
        print("\n" + "=" * 80)
        print("SPECIFIC CHECK: CF-05-1")
        print("=" * 80)
        
        cf_05_1 = db.query(Experiment).filter(
            Experiment.experiment_id == "CF-05-1"
        ).first()
        
        if cf_05_1:
            print(f"\n✓ Found CF-05-1 (ID: {cf_05_1.id})")
            print(f"  base_experiment_id: {cf_05_1.base_experiment_id}")
            print(f"  parent_experiment_fk: {cf_05_1.parent_experiment_fk}")
            parsed = parse_experiment_id("CF-05-1")
            print(f"  Parsed as: base={parsed[0]}, seq={parsed[1]}, treatment={parsed[2]}")
        
        print("\n" + "=" * 80)
        
    except Exception as e:
        print(f"Error during check: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_lineage_integrity()

