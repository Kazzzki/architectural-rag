import traceback
from typing import List
from core.models_v2 import PlanV2
from adapters.excel_adapter import ExcelAdapter

class RunResultV2:
    def __init__(self, success: bool, output_path: str = "", error_message: str = "", logs: List[str] = None):
        self.success = success
        self.output_path = output_path
        self.error_message = error_message
        self.logs = logs or []
        
    def to_dict(self):
        return {
            "success": self.success,
            "output_path": self.output_path,
            "error_message": self.error_message,
            "logs": self.logs
        }

def execute_v2(plan: PlanV2, working_path: str, output_dir: str, logs_dir: str) -> RunResultV2:
    """
    Phase 6: Execution
    Applies the validated PlanV2 operations to the working file and saves to output.
    """
    logs = []
    try:
        adapter = ExcelAdapter(working_path)
        
        for i, op in enumerate(plan.operations):
            logs.append(f"Executing: {op.op} on {op.sheet} | params: {op.params}")
            
            sheet = op.sheet
            params = op.params
            
            if op.op == "insert_column":
                adapter.insert_column(sheet, params["idx"], params["header_name"])
            elif op.op == "write_cell":
                adapter.write_cell(sheet, params["row"], params["col"], params["value"])
            elif op.op == "write_range":
                adapter.write_range(sheet, params["start_row"], params["start_col"], params["data"])
            elif op.op == "set_formula":
                adapter.set_formula(sheet, params["row"], params["col"], params["formula"])
            elif op.op == "fill_down":
                adapter.fill_down(sheet, params["col"], params["start_row"], params["end_row"], params["formula"])
            elif op.op == "set_number_format":
                adapter.set_number_format(sheet, params["row"], params["col"], params["number_format"])
            elif op.op == "add_sheet":
                adapter.add_sheet(sheet)
            else:
                raise ValueError(f"Unknown operation: {op.op}")
                
        output_path = plan.output_file
        adapter.save_as(output_path)
        logs.append(f"Saved successfully to {output_path}")
        return RunResultV2(success=True, output_path=output_path, logs=logs)
        
    except Exception as e:
        err = traceback.format_exc()
        logs.append(f"ERROR: {e}\n{err}")
        return RunResultV2(success=False, error_message=str(e), logs=logs)
