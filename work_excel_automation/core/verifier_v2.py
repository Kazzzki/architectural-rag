import json
import os
from typing import Dict, Any, List
from core.models_v2 import PlanV2
from core.profiling import profile_workbook

class VerifyReportV2:
    def __init__(self, run_id: str, success: bool, diff_summary: Dict[str, Any], failed_validations: List[str]):
        self.run_id = run_id
        self.success = success
        self.diff_summary = diff_summary
        self.failed_validations = failed_validations
        
    def to_dict(self):
        return {
            "run_id": self.run_id,
            "success": self.success,
            "diff_summary": self.diff_summary,
            "failed_validations": self.failed_validations
        }

def verify_v2(plan: PlanV2, before_path: str, after_path: str, file_info: dict, logs_dir: str) -> VerifyReportV2:
    """
    Phase 7: Verification
    Verifies that the output file correctly matches the plan's intent securely, checking against original manifest.
    """
    success = True
    failed_validations = []
    diff_summary = {}

    if not os.path.exists(after_path):
        success = False
        failed_validations.append("Output file does not exist.")
        report = VerifyReportV2(run_id=plan.run_id, success=success, diff_summary=diff_summary, failed_validations=failed_validations)
        _save_report(report, logs_dir, plan.run_id)
        return report

    # Generate fresh manifests for strict comparison
    before_manifest = profile_workbook(plan.run_id, before_path, file_info)
    after_manifest = profile_workbook(plan.run_id, after_path, file_info)
    
    # Check unintended sheet changes
    for val in plan.validations:
        if val.type == "no_unintended_sheet_changes":
            intended_sheets = set(op.sheet for op in plan.operations)
            before_sheets = {s.sheet_name: s for s in before_manifest.sheets}
            after_sheets = {s.sheet_name: s for s in after_manifest.sheets}
            
            for sheet_name, before_sheet in before_sheets.items():
                if sheet_name not in intended_sheets:
                    after_sheet = after_sheets.get(sheet_name)
                    if not after_sheet or before_sheet.used_range != after_sheet.used_range:
                        success = False
                        failed_validations.append(f"Unintended configuration/dimension change on sheet {sheet_name}")
                        
    diff_summary["sheets_before"] = [s.sheet_name for s in before_manifest.sheets]
    diff_summary["sheets_after"] = [s.sheet_name for s in after_manifest.sheets]
    diff_summary["dimensions_changed"] = {
        s: {"before": b.used_range, "after": a.used_range}
        for s in set(diff_summary["sheets_before"] + diff_summary["sheets_after"])
        for b in [next((sh for sh in before_manifest.sheets if sh.sheet_name == s), None)]
        for a in [next((sh for sh in after_manifest.sheets if sh.sheet_name == s), None)]
        if b and a and b.used_range != a.used_range
    }

    report = VerifyReportV2(
        run_id=plan.run_id,
        success=success,
        diff_summary=diff_summary,
        failed_validations=failed_validations
    )
    
    _save_report(report, logs_dir, plan.run_id)
    return report

def _save_report(report: VerifyReportV2, logs_dir: str, run_id: str):
    os.makedirs(logs_dir, exist_ok=True)
    verify_log_path = os.path.join(logs_dir, f"{run_id}__verify.json")
    with open(verify_log_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
