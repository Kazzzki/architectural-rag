import os
from typing import Dict, Any, List
from adapters.excel_adapter import ExcelAdapter
from core.models_v2 import WorkbookManifest, SheetManifest, FileInfo, WorkbookMeta, ColumnProfile

def profile_workbook(run_id: str, working_path: str, file_info_dict: Dict[str, Any]) -> WorkbookManifest:
    """
    Phase 2: Discovery -> Detailed Workbook Profiling
    Reads an Excel file and deeply analyzes its contents, returning a WorkbookManifest.
    """
    adapter = ExcelAdapter(working_path)
    sheets = adapter.get_sheets()
    
    file_info = FileInfo(**file_info_dict)
    
    wb_meta = WorkbookMeta(
        sheet_count=len(sheets),
        protected=False # Placeholder for wb-level protections
    )
    
    sheet_manifests = []
    for sheet in sheets:
        dims = adapter.get_used_range(sheet)
        indices = adapter.get_used_range_indices(sheet)
        hidden_rows = adapter.get_hidden_rows(sheet)
        hidden_cols = adapter.get_hidden_cols(sheet)
        merged_cells = adapter.get_merged_cells(sheet)
        is_protected = adapter.is_sheet_protected(sheet)
        
        try:
            formula_regions = adapter.get_formula_regions(sheet)
        except Exception:
            formula_regions = []
            
        # Basic heuristic for headers: get top 15 rows
        max_preview_row = min(15, indices["end"][0] if indices["end"][0] > 0 else 1)
        # Avoid huge ranges
        max_preview_col = min(100, indices["end"][1] if indices["end"][1] > 0 else 1)
        
        try:
            raw_data = adapter.read_range(
                sheet, 
                min_row=max(1, indices["start"][0]), 
                max_row=max_preview_row, 
                min_col=max(1, indices["start"][1]), 
                max_col=max_preview_col
            )
        except Exception:
            raw_data = []

        header_candidates = []
        for i, row in enumerate(raw_data):
            if any(c is not None and str(c).strip() for c in row):
                header_candidates.append({
                    "row": i + 1,
                    "values": [str(c) if c is not None else "" for c in row]
                })

        table_candidates = [{"start_row": 1, "end_row": indices["end"][0]}]
        
        column_profiles = []
        # Sample for column profiling (top 100 rows)
        sample_max_row = min(100, indices["end"][0] if indices["end"][0] > 0 else 1)
        try:
            sample_data = adapter.read_range(
                sheet, 
                min_row=1, 
                max_row=sample_max_row, 
                min_col=max(1, indices["start"][1]), 
                max_col=max_preview_col
            )
        except Exception:
            sample_data = []

        if sample_data:
            col_count = len(sample_data[0]) if sample_data else 0
            for col_idx in range(col_count):
                vals = []
                for row in sample_data:
                    if len(row) > col_idx and row[col_idx] is not None and str(row[col_idx]).strip() != "":
                        vals.append(row[col_idx])
                        
                null_ratio = 1.0 - (len(vals) / max(1, len(sample_data)))
                unique_est = len(set(str(v) for v in vals))
                
                inferred_type = "string"
                if vals and all(isinstance(v, (int, float)) for v in vals):
                    inferred_type = "numeric"
                    
                col_label = f"Col_{col_idx+1}"
                if header_candidates and len(header_candidates[0]["values"]) > col_idx:
                    col_label = header_candidates[0]["values"][col_idx]

                column_profiles.append(ColumnProfile(
                    col_idx=col_idx+1,
                    col_label=col_label,
                    inferred_type=inferred_type,
                    null_ratio=round(null_ratio, 2),
                    unique_est=unique_est
                ))

        risk_flags = []
        if hidden_cols: risk_flags.append("has_hidden_columns")
        if hidden_rows: risk_flags.append("has_hidden_rows")
        if merged_cells: risk_flags.append("has_merged_cells")
        if is_protected: risk_flags.append("sheet_protected")
        if len(header_candidates) > 2: risk_flags.append("multi_level_headers_detected")
        
        sheet_manifests.append(SheetManifest(
            sheet_name=sheet,
            dimensions=dims,
            used_range=indices,
            hidden_rows=hidden_rows,
            hidden_cols=hidden_cols,
            merged_cells=merged_cells,
            header_candidates=header_candidates,
            table_candidates=table_candidates,
            formula_regions=formula_regions,
            column_profiles=column_profiles,
            risk_flags=risk_flags,
            profiling_confidence=0.85
        ))
        
    return WorkbookManifest(
        manifest_version="1.0",
        run_id=run_id,
        file_info=file_info,
        workbook_meta=wb_meta,
        sheets=sheet_manifests
    )
