import json
from core.models_v2 import WorkbookManifest
from core.profile_matcher_v2 import match_profile_v2
from core.recovery_v2 import detect_recovery_diff

def test():
    with open("data/manifests/test_sales_manifest.json") as f:
        manifest_v1 = WorkbookManifest.from_dict(json.load(f))
        
    print("Testing Profile Matching V2...")
    match = match_profile_v2(manifest_v1, "profiles")
    print(f"Match Result: {match.to_dict()}")
    
    # Create an artificial shifted manifest
    import copy
    manifest_v2 = copy.deepcopy(manifest_v1)
    
    # Change a column to simulate shift
    manifest_v2.sheets[0].column_profiles[2].col_idx = 4
    # Rename a column
    manifest_v2.sheets[0].column_profiles[0].col_label = "年月日"
    
    print("\nTesting Recovery Diff...")
    diff = detect_recovery_diff(manifest_v1, manifest_v2)
    print(json.dumps(diff, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test()
