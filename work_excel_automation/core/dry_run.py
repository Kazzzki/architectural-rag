from core.models import Plan, DryRunReport, DiscoverySummary

def dry_run(plan: Plan, summary: DiscoverySummary, max_changed_cells: int = 100000) -> DryRunReport:
    """
    Phase 5: Dry Run
    Validates preconditions and estimates impact.
    Stops if preconditions fail or exceed safety thresholds.
    """
    changed_sheets = list(set(op.sheet for op in plan.operations))
    
    stop_reason = None
    preconditions_met = True
    
    for prec in plan.preconditions:
        if prec.type == "sheet_exists":
            if prec.sheet not in summary.sheets:
                preconditions_met = False
                stop_reason = f"Precondition failed: Sheet '{prec.sheet}' does not exist."
                break
                
    # Estimate cells changed (very roughly for PoC)
    cells_changed = 0
    for op in plan.operations:
        if op.op == "write_cell":
            cells_changed += 1
        elif op.op == "write_range":
            # rough estimate if data is present
            data = op.params.get("data", [[]])
            cells_changed += sum(len(row) for row in data)
        elif op.op == "set_formula":
            cells_changed += 1
        elif op.op == "fill_down":
            start = op.params.get("start_row", 1)
            end = op.params.get("end_row", 1)
            cells_changed += max(0, end - start + 1)
        elif op.op == "insert_column":
            cells_changed += 100 # arbitrary placeholder
            
    if preconditions_met and cells_changed > max_changed_cells:
        preconditions_met = False
        stop_reason = f"Safety limit exceeded: Estimated {cells_changed} cells changed (max: {max_changed_cells})"
    
    return DryRunReport(
        run_id=plan.run_id,
        changed_sheets=changed_sheets,
        estimated_cells_changed=cells_changed,
        columns_added=sum(1 for op in plan.operations if op.op == "insert_column"),
        columns_removed=0,
        formula_changes=sum(1 for op in plan.operations if op.op in ["set_formula", "fill_down"]),
        preconditions_met=preconditions_met,
        stop_reason=stop_reason
    )
