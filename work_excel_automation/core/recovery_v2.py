from core.models_v2 import WorkbookManifest

def detect_recovery_diff(old_manifest: WorkbookManifest, new_manifest: WorkbookManifest) -> dict:
    """
    Phase 2: Recovery Mode
    Compares an old (known working) manifest against a newly generated one
    to detect structural shifts like moved or renamed columns.
    """
    diff = {
        "sheets_added": [],
        "sheets_removed": [],
        "columns_moved": [],
        "columns_added": [],
        "columns_removed": []
    }
    
    old_sheets = {s.sheet_name: s for s in old_manifest.sheets}
    new_sheets = {s.sheet_name: s for s in new_manifest.sheets}
    
    for s_name in new_sheets:
        if s_name not in old_sheets:
            diff["sheets_added"].append(s_name)
            
    for s_name in old_sheets:
        if s_name not in new_sheets:
            diff["sheets_removed"].append(s_name)
            
    # Check column changes for sheets that exist in both
    for s_name in old_sheets:
        if s_name in new_sheets:
            old_s = old_sheets[s_name]
            new_s = new_sheets[s_name]
            
            old_cols = {c.col_label: c.col_idx for c in old_s.column_profiles if c.col_label}
            new_cols = {c.col_label: c.col_idx for c in new_s.column_profiles if c.col_label}
            
            for c_name, n_idx in new_cols.items():
                if c_name not in old_cols:
                    diff["columns_added"].append({"sheet": s_name, "column": c_name, "idx": n_idx})
                elif old_cols[c_name] != n_idx:
                    diff["columns_moved"].append({
                        "sheet": s_name, 
                        "column": c_name, 
                        "old_idx": old_cols[c_name], 
                        "new_idx": n_idx
                    })
                    
            for c_name, o_idx in old_cols.items():
                if c_name not in new_cols:
                    diff["columns_removed"].append({"sheet": s_name, "column": c_name, "idx": o_idx})
                    
    return diff
