import traceback
from core.models import Plan, ExecuteResult
from adapters.excel_adapter import ExcelAdapter
from adapters.logger import RunLogger
from adapters.file_io import make_output_path

def execute(plan: Plan, working_path: str, output_dir: str, logs_dir: str) -> ExecuteResult:
    """
    Phase 6: Execution
    Applies operations from Plan to the working file and saves to output_dir.
    """
    logger = RunLogger(logs_dir, plan.run_id)
    adapter = ExcelAdapter(working_path)
    
    success = True
    error_msg = None
    executed = 0
    output_path = None
    
    try:
        for op in plan.operations:
            try:
                if op.op == "insert_column":
                    idx = op.params["idx"]
                    header_name = op.params["header_name"]
                    adapter.insert_column(op.sheet, idx, header_name)
                    
                elif op.op == "write_cell":
                    row = op.params["row"]
                    col = op.params["col"]
                    val = op.params["value"]
                    adapter.write_cell(op.sheet, row, col, val)
                    
                elif op.op == "write_range":
                    row = op.params["start_row"]
                    col = op.params["start_col"]
                    data = op.params["data"]
                    adapter.write_range(op.sheet, row, col, data)
                    
                elif op.op == "set_formula":
                    row = op.params["row"]
                    col = op.params["col"]
                    formula = op.params["formula"]
                    adapter.set_formula(op.sheet, row, col, formula)
                    
                elif op.op == "fill_down":
                    col = op.params["col"]
                    start_row = op.params["start_row"]
                    end_row = op.params["end_row"]
                    formula = op.params["formula"]
                    adapter.fill_down(op.sheet, col, start_row, end_row, formula)
                    
                elif op.op == "set_number_format":
                    row = op.params["row"]
                    col = op.params["col"]
                    fmt = op.params["format"]
                    adapter.set_number_format(op.sheet, row, col, fmt)
                    
                elif op.op == "add_sheet":
                    sheet_name = op.params["sheet_name"]
                    adapter.add_sheet(sheet_name)
                    
                else:
                    raise ValueError(f"Unknown operation: {op.op}")
                    
                logger.log_operation(op.op, op.sheet, "success", op.reason)
                executed += 1
                
            except Exception as e:
                logger.log_operation(op.op, op.sheet, "error", str(e))
                raise e
                
        output_path = make_output_path(plan.input_file, output_dir, plan.run_id)
        adapter.save_as(output_path)
        
    except Exception as e:
        success = False
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
    finally:
        logger.save()
        
    return ExecuteResult(
        run_id=plan.run_id,
        success=success,
        output_path=output_path,
        error_message=error_msg,
        executed_operations=executed
    )
