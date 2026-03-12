from typing import Dict, Any, List
from core.models import DiscoverySummary
from adapters.excel_adapter import ExcelAdapter

def discover(working_path: str) -> DiscoverySummary:
    """
    Phase 2: Discovery (v2)
    Reads the working file to extract raw structure (top 20 rows + merged cells).
    Does NOT attempt to infer headers or data types programmatically.
    """
    adapter = ExcelAdapter(working_path)
    sheets = adapter.get_sheets()
    
    dimensions = {}
    raw_data = {}
    merged_cells = {}
    
    for sheet in sheets:
        dims = adapter.get_used_range(sheet)
        dimensions[sheet] = dims
        merged_cells[sheet] = adapter.get_merged_cells(sheet)
        
        # Read a larger area for preview to capture wide/long tables (e.g. 100 rows, 300 cols)
        preview_data = adapter.read_range(sheet, min_row=1, max_row=100, min_col=1, max_col=300, data_only=True)
        
        # Trim completely empty trailing columns for each row
        trimmed_preview = []
        for row in preview_data:
            while row and row[-1] is None:
                row.pop()
            trimmed_preview.append(row)
            
        raw_data[sheet] = trimmed_preview

    return DiscoverySummary(
        sheets=sheets,
        dimensions=dimensions,
        raw_data=raw_data,
        merged_cells=merged_cells
    )
