import json
from mcp.server.fastmcp import FastMCP
from adapters.excel_adapter import ExcelAdapter

mcp = FastMCP("ExcelFlow-LowLevel")

@mcp.tool()
def list_sheets(file_path: str) -> str:
    """List sheets in an Excel file."""
    try:
        adapter = ExcelAdapter(file_path)
        return json.dumps(adapter.get_sheets(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def read_range(file_path: str, sheet: str, min_row: int, max_row: int, min_col: int, max_col: int) -> str:
    """Read a specific range from an Excel file."""
    try:
        adapter = ExcelAdapter(file_path)
        data = adapter.read_range(sheet, min_row, max_row, min_col, max_col)
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def diff_summary() -> str:
    """Returns a basic diff (Not fully implemented in low-level for PoC)."""
    return "Not implemented directly in low-level. Use High-level verifier."

if __name__ == "__main__":
    mcp.run()
