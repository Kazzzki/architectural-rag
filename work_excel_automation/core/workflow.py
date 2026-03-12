import os
from core.intake import intake
from core.discovery import discover
from core.profile_matcher import match_profile
from core.planner import build_plan
from core.dry_run import dry_run
from core.executor import execute
from core.verifier import verify

def run_workflow_poc(
    input_file: str,
    base_dir: str,
    operations_spec: list,
    profiles_dir: str
):
    inbox_dir = os.path.join(base_dir, "data", "inbox")
    working_dir = os.path.join(base_dir, "data", "working")
    output_dir = os.path.join(base_dir, "data", "output")
    plans_dir = os.path.join(base_dir, "data", "plans")
    logs_dir = os.path.join(base_dir, "data", "logs")
    
    # 1. Intake
    intake_res = intake(input_file, working_dir)
    print(f"Intake: Run ID {intake_res.run_id}")
    
    # 2. Discovery
    summary = discover(intake_res.working_path)
    print(f"Discovery: Found {len(summary.sheets)} sheets")
    
    # 3. Profile Match
    match_res = match_profile(summary, profiles_dir)
    print(f"Match: {match_res.matched_profile_id} (Score: {match_res.score})")
    
    # 4. Plan
    plan = build_plan(
        intake_res.run_id, 
        input_file, 
        intake_res.working_path, 
        summary, 
        match_res, 
        operations_spec, 
        plans_dir
    )
    print("Plan built.")
    
    # 5. Dry Run
    dr_report = dry_run(plan, summary)
    if not dr_report.preconditions_met:
        print(f"Dry Run failed: {dr_report.stop_reason}")
        return
    print("Dry Run passed.")
    
    # 6. Execute
    exec_res = execute(plan, intake_res.working_path, output_dir, logs_dir)
    if not exec_res.success:
        print(f"Execute failed: {exec_res.error_message}")
        return
    print(f"Execute success. Output at {exec_res.output_path}")
    
    # 7. Verify
    ver_report = verify(plan, intake_res.working_path, exec_res.output_path, logs_dir)
    print(f"Verify success: {ver_report.success}")
    return ver_report
