import json
import os
from core.models import Plan, VerifyReport
from core.discovery import discover

def verify(plan: Plan, before_path: str, after_path: str, logs_dir: str) -> VerifyReport:
    """
    Phase 7: Verification
    Verifies the output file matches the plan's intent securely.
    """
    success = True
    failed_validations = []
    diff_summary = {}

    if not os.path.exists(after_path):
        success = False
        failed_validations.append("Output file does not exist.")
        report = VerifyReport(run_id=plan.run_id, success=success, diff_summary=diff_summary, failed_validations=failed_validations)
        _save_report(report, logs_dir, plan.run_id)
        return report

    before_summary = discover(before_path)
    after_summary = discover(after_path)
    
    # Check unintended sheet changes
    for val in plan.validations:
        if val.type == "no_unintended_sheet_changes":
            intended_sheets = set(op.sheet for op in plan.operations)
            for sheet in before_summary.sheets:
                if sheet not in intended_sheets:
                    if before_summary.dimensions.get(sheet) != after_summary.dimensions.get(sheet):
                        success = False
                        failed_validations.append(f"Unintended dimension change on sheet {sheet}")
                        
    diff_summary["sheets_before"] = before_summary.sheets
    diff_summary["sheets_after"] = after_summary.sheets
    diff_summary["dimensions_changed"] = {
        s: {"before": before_summary.dimensions.get(s), "after": after_summary.dimensions.get(s)}
        for s in set(before_summary.sheets + after_summary.sheets)
        if before_summary.dimensions.get(s) != after_summary.dimensions.get(s)
    }

    report = VerifyReport(
        run_id=plan.run_id,
        success=success,
        diff_summary=diff_summary,
        failed_validations=failed_validations
    )
    
    _save_report(report, logs_dir, plan.run_id)
    return report

def _save_report(report: VerifyReport, logs_dir: str, run_id: str):
    os.makedirs(logs_dir, exist_ok=True)
    verify_log_path = os.path.join(logs_dir, f"{run_id}__verify.json")
    with open(verify_log_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
