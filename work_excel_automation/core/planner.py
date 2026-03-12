import json
import os
from typing import Dict, Any, List
from core.models import DiscoverySummary, MatchResult, Plan, Operation, Precondition, Validation
from adapters.file_io import make_plan_path

def build_plan(
    run_id: str,
    input_file: str,
    output_file: str,
    summary: DiscoverySummary,
    match_result: MatchResult,
    operations_spec: List[Dict[str, Any]],
    plans_dir: str
) -> Plan:
    """
    Phase 4: Planning
    Constructs a detailed JSON plan based on matched profile and requested ops.
    """
    operations = []
    for op_dict in operations_spec:
        operations.append(Operation(
            op=op_dict["op"],
            sheet=op_dict["sheet"],
            params=op_dict.get("params", {}),
            reason=op_dict.get("reason", "No reason provided")
        ))
        
    preconditions = []
    target_sheets = set(op.sheet for op in operations)
    for sheet in target_sheets:
        preconditions.append(Precondition(type="sheet_exists", value=True, sheet=sheet))
        
    validations = []
    validations.append(Validation(type="no_unintended_sheet_changes"))

    plan = Plan(
        run_id=run_id,
        input_file=input_file,
        output_file=output_file,
        matched_profile=match_result.matched_profile_id,
        operations=operations,
        preconditions=preconditions,
        validations=validations
    )
    
    plan_path = make_plan_path(plans_dir, input_file, run_id)
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan.to_dict(), f, indent=2, ensure_ascii=False)
        
    return plan
    
def load_plan(plan_path: str) -> Plan:
    with open(plan_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Plan.from_dict(data)
