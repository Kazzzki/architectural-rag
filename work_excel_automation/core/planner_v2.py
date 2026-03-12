import json
import os
from typing import List, Dict, Any
from core.models_v2 import PlanV2, OperationV2, PreconditionV2, ValidationV2

def build_plan_v2(
    run_id: str,
    input_file: str,
    matched_profile: str,
    manifest_ref: str,
    mapping_ref: str,
    write_contract_ref: str,
    raw_ops: List[Dict[str, Any]],
    out_dir: str
) -> PlanV2:
    """
    Phase 4: Planning
    Constructs a formal PlanV2 from a list of desired operations.
    """
    operations = []
    for op_dict in raw_ops:
        operations.append(OperationV2(
            op=op_dict["op"],
            sheet=op_dict["sheet"],
            params=op_dict.get("params", {}),
            reason=op_dict.get("reason", "No reason provided")
        ))
        
    # Default precondition to verify target sheet exists
    # Contract enforcement is defined as a validation step
    validations = [
        ValidationV2(type="contract_enforcement", params={}),
        ValidationV2(type="no_unintended_sheet_changes", params={})
    ]
    
    # Simple sheet preconditions based on target sheets in operations
    target_sheets = set(op.sheet for op in operations)
    preconditions = [PreconditionV2(type="sheet_exists", sheet=s) for s in target_sheets]
    
    plan = PlanV2(
        version="1.0",
        run_id=run_id,
        input_file=input_file,
        output_file=input_file.replace("working", "output").replace("__wrk_", "__out_"), # Simplified output name mapping
        matched_profile=matched_profile,
        manifest_ref=manifest_ref,
        mapping_ref=mapping_ref,
        write_contract_ref=write_contract_ref,
        preconditions=preconditions,
        operations=operations,
        validations=validations,
        approval_required=True
    )
    
    os.makedirs(out_dir, exist_ok=True)
    filename = os.path.basename(input_file).replace(".xlsx", "")
    out_path = os.path.join(out_dir, f"{filename}__plan_{run_id}.json")
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(plan.to_dict(), f, indent=2, ensure_ascii=False)
        
    return plan

def load_plan_v2(filepath: str) -> PlanV2:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return PlanV2.from_dict(data)
