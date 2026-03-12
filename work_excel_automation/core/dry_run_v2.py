from openpyxl.utils.cell import range_boundaries, coordinate_from_string, column_index_from_string
from core.models_v2 import PlanV2, WorkbookManifest
from core.contracts import load_contract

class DryRunError(Exception):
    pass

def check_overlap(r1_min_col, r1_min_row, r1_max_col, r1_max_row, r2_min_col, r2_min_row, r2_max_col, r2_max_row):
    # If one rectangle is on left side of other
    if r1_min_col > r2_max_col or r2_min_col > r1_max_col:
        return False
    # If one rectangle is above other
    if r1_min_row > r2_max_row or r2_min_row > r1_max_row:
        return False
    return True

def validate_write_contract(plan: PlanV2):
    """
    Validates that the operations in the Plan do not violate the Write Contract.
    """
    try:
        contract = load_contract(plan.write_contract_ref)
    except FileNotFoundError:
        # If no contract generated/linked, we must fail secure
        raise DryRunError("WriteContract not found. Safe Mode blocks execution without a contract.")

    # Parse read only ranges (e.g. ['A1:F1048576'])
    read_only = []
    for rng in contract.read_only_ranges:
        read_only.append(range_boundaries(rng))
        
    for op in plan.operations:
        if op.op in contract.forbidden_operations:
            raise DryRunError(f"Forbidden operation '{op.op}' attempted on sheet {op.sheet}.")
            
        if op.sheet != contract.target_sheet:
            # For MVP, restrict operations exclusively to target sheet defined in contract
            raise DryRunError(f"Operation on unauthorized sheet: {op.sheet}")

        op_bounds = None
        if op.op == "write_cell" or op.op == "set_formula":
            col = op.params.get("col", 1)
            row = op.params.get("row", 1)
            op_bounds = (col, row, col, row)
            
        elif op.op == "write_range":
            start_col = op.params.get("start_col", 1)
            start_row = op.params.get("start_row", 1)
            data = op.params.get("data", [[]])
            max_col = start_col + len(data[0]) - 1 if data else start_col
            max_row = start_row + len(data) - 1
            op_bounds = (start_col, start_row, max_col, max_row)
            
        elif op.op == "fill_down":
            col = op.params.get("col", 1)
            start_row = op.params.get("start_row", 1)
            end_row = op.params.get("end_row", 1)
            op_bounds = (col, start_row, col, end_row)
            
        elif op.op == "insert_column":
            col = op.params.get("idx", 1)
            # inserting a column effectively shifts things, but the insert itself happens at a column
            # In excel, 1048576 is max row.
            op_bounds = (col, 1, col, 1048576)

        if op_bounds:
            # Check overlap against read-only ranges
            for ro in read_only: # (min_col, min_row, max_col, max_row)
                if check_overlap(*op_bounds, *ro):
                    raise DryRunError(f"Operation '{op.op}' overlaps with read-only range {ro}")

    return True

def dry_run_v2(plan: PlanV2, manifest: WorkbookManifest, max_changed_cells: int = 100000) -> dict:
    preconditions_met = True
    stop_reason = None
    
    # 1. Preconditions
    sheet_names = [s.sheet_name for s in manifest.sheets]
    for prec in plan.preconditions:
        if prec.type == "sheet_exists":
            if prec.sheet not in sheet_names:
                preconditions_met = False
                stop_reason = f"Precondition failed: Sheet '{prec.sheet}' does not exist."
                break

    # 2. Write Contract Validation
    if preconditions_met:
        try:
            validate_write_contract(plan)
        except DryRunError as e:
            preconditions_met = False
            stop_reason = f"Write Contract Violation: {str(e)}"

    # 3. Size Estimates
    cells_changed = 0
    for op in plan.operations:
        if op.op in ["write_cell", "set_formula", "set_number_format"]:
            cells_changed += 1
        elif op.op == "write_range":
            data = op.params.get("data", [[]])
            cells_changed += sum(len(row) for row in data)
        elif op.op == "fill_down":
            start = op.params.get("start_row", 1)
            end = op.params.get("end_row", 1)
            cells_changed += max(0, end - start + 1)
        elif op.op == "insert_column":
            cells_changed += 100 # arbitrary placeholder
            
    if preconditions_met and cells_changed > max_changed_cells:
        preconditions_met = False
        stop_reason = f"Safety limit exceeded: Estimated {cells_changed} cells changed (max: {max_changed_cells})"

    return {
        "run_id": plan.run_id,
        "preconditions_met": preconditions_met,
        "estimated_cells_changed": cells_changed,
        "stop_reason": stop_reason,
        "success": preconditions_met
    }
