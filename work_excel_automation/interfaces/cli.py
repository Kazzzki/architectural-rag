import argparse
import json
import sys
import os
from pathlib import Path
from core.intake import intake_file
from core.profiling import profile_workbook
from core.planner_v2 import build_plan_v2, load_plan_v2
from core.dry_run_v2 import dry_run_v2
from core.executor_v2 import execute_v2
import uuid
from core.verifier_v2 import verify_v2
from core.trusted_mode import evaluate_trusted_mode

def get_base_dir():
    return os.getcwd()
    
def get_dirs():
    base = get_base_dir()
    return {
        "inbox": os.path.join(base, "data", "inbox"),
        "working": os.path.join(base, "data", "working"),
        "output": os.path.join(base, "data", "output"),
        "plans": os.path.join(base, "data", "plans"),
        "logs": os.path.join(base, "data", "logs"),
        "profiles": os.path.join(base, "profiles")
    }

def handle_discover(args):
    dirs = get_dirs()
    try:
        run_id, working_path, file_info = intake_file(args.input, dirs["working"])
        manifest = profile_workbook(run_id, working_path, file_info)
        
        manifest_dict = manifest.to_dict()
        
        if args.out_manifest:
            with open(args.out_manifest, "w", encoding="utf-8") as f:
                json.dump(manifest_dict, f, indent=2, ensure_ascii=False)
            print(f"Manifest saved to {args.out_manifest}")
            
        if args.json:
            print(json.dumps(manifest_dict, indent=2, ensure_ascii=False))
        else:
            print(f"Discovered {len(manifest.sheets)} sheets in {args.input}. Run ID: {run_id}")
            for s in manifest.sheets:
                print(f" - {s.sheet_name}: {s.dimensions} (Risk flags: {s.risk_flags})")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

def handle_plan(args):
    dirs = get_dirs()
    try:
        with open(args.ops, "r", encoding="utf-8") as f:
            ops_spec = json.load(f)
            
        plan = build_plan_v2(
            run_id=args.run_id or "run_test_v2",
            input_file=args.input,
            matched_profile=args.profile or "default",
            manifest_ref=args.manifest,
            mapping_ref=args.mapping,
            write_contract_ref=args.contract,
            raw_ops=ops_spec,
            out_dir=dirs["plans"]
        )
        
        if args.json:
            print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Created Plan: {plan.run_id}")
            print(f"Saved to {dirs['plans']}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(2)

def handle_run(args):
    dirs = get_dirs()
    try:
        plan = load_plan_v2(args.plan)
        
        # In this flow, working file is directly specified in Plan input_file
        working_file = plan.input_file
        if not os.path.exists(working_file):
            print(f"Working file not found: {working_file}. Ensure you copied to working directory.", file=sys.stderr)
            sys.exit(2)
            
        with open(plan.manifest_ref, "r", encoding="utf-8") as f:
            from core.models_v2 import WorkbookManifest
            manifest_dict = json.load(f)
            manifest = WorkbookManifest.from_dict(manifest_dict)
            
        dr_report = dry_run_v2(plan, manifest)
        
        if args.dry_run:
            if args.json:
                print(json.dumps(dr_report, indent=2, ensure_ascii=False))
            else:
                print(f"Dry Run Report: {dr_report['stop_reason'] or 'Success'}")
            sys.exit(0 if dr_report["success"] else 1)
            
        if not dr_report["success"]:
            print(f"Preconditions/Contract failed: {dr_report['stop_reason']}", file=sys.stderr)
            sys.exit(1)
            
        exec_res = execute_v2(plan, working_file, dirs["output"], dirs["logs"])
        if args.json:
            print(json.dumps(exec_res.to_dict(), indent=2, ensure_ascii=False))
        else:
            if exec_res.success:
                print(f"Execute success! Saved to {exec_res.output_path}")
            else:
                print(f"Execute failed: {exec_res.error_message}", file=sys.stderr)
                sys.exit(2)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(2)

def handle_verify(args):
    dirs = get_dirs()
    try:
        plan = load_plan_v2(args.plan)
        
        # We need mock file_info for the verify run
        file_info = {
            "filename": os.path.basename(args.after),
            "extension": os.path.splitext(args.after)[1],
            "size_bytes": os.path.getsize(args.after),
            "hash": "sha256:unknown_runtime_verify"
        }
        
        report = verify_v2(plan, args.before, args.after, file_info, dirs["logs"])
        if args.json:
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Verify Success: {report.success}")
            if not report.success:
                print("Failed Validations:", report.failed_validations)
            sys.exit(0 if report.success else 3)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(2)

def handle_trust(args):
    # Evaluates whether a sheet context can bypass HITL
    try:
        from core.models_v2 import WorkbookManifest
        from core.profile_matcher_v2 import match_profile_v2
        from core.contracts import load_contract
        
        with open(args.manifest, "r", encoding="utf-8") as f:
            manifest = WorkbookManifest.from_dict(json.load(f))
            
        contract = load_contract(args.contract)
        match_result = match_profile_v2(manifest, get_dirs()["profiles"])
        
        trust_eval = evaluate_trusted_mode(manifest, match_result, contract)
        
        if args.json:
            print(json.dumps(trust_eval.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Is Trusted: {trust_eval.is_trusted}")
            for r in trust_eval.reasons:
                print(f" - {r}")
                
        sys.exit(0 if trust_eval.is_trusted else 4)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(2)

def main():
    parser = argparse.ArgumentParser(prog="excelflow", description="ExcelFlow CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # discover
    p_disc = subparsers.add_parser("discover", help="Discover structure of an Excel file (HITL v2)")
    p_disc.add_argument("--input", required=True, help="Input Excel file")
    p_disc.add_argument("--out_manifest", help="Optional path to output the Manifest JSON")
    p_disc.add_argument("--json", action="store_true", help="Output as JSON to stdout")
    
    # plan
    p_plan = subparsers.add_parser("plan", help="Generate edit plan")
    p_plan.add_argument("--run_id", help="Override run_id")
    p_plan.add_argument("--input", required=True, help="Input Excel file (Working copy)")
    p_plan.add_argument("--profile", help="Matched profile ID")
    p_plan.add_argument("--manifest", required=True, help="Manifest JSON reference")
    p_plan.add_argument("--mapping", required=True, help="Mapping Spec JSON reference")
    p_plan.add_argument("--contract", required=True, help="Write Contract JSON reference")
    p_plan.add_argument("--ops", required=True, help="JSON file containing operations list")
    p_plan.add_argument("--json", action="store_true", help="Output as JSON")
    
    # run
    p_run = subparsers.add_parser("run", help="Execute a plan")
    p_run.add_argument("--plan", required=True, help="Plan JSON file path")
    p_run.add_argument("--dry-run", action="store_true", help="Only run dry run")
    p_run.add_argument("--json", action="store_true", help="Output as JSON")
    
    # verify
    p_ver = subparsers.add_parser("verify", help="Verify execution result")
    p_ver.add_argument("--plan", required=True, help="Plan JSON file path")
    p_ver.add_argument("--before", required=True, help="Path to working file (before execute)")
    p_ver.add_argument("--after", required=True, help="Path to output file (after execute)")
    p_ver.add_argument("--json", action="store_true", help="Output as JSON")
    
    # evaluate-trust
    p_trust = subparsers.add_parser("evaluate-trust", help="Evaluate if HITL bypass is permitted")
    p_trust.add_argument("--manifest", required=True, help="Manifest JSON")
    p_trust.add_argument("--contract", required=True, help="Write Contract JSON")
    p_trust.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if args.command == "discover":
        handle_discover(args)
    elif args.command == "plan":
        handle_plan(args)
    elif args.command == "run":
        handle_run(args)
    elif args.command == "verify":
        handle_verify(args)
    elif args.command == "evaluate-trust":
        handle_trust(args)

if __name__ == "__main__":
    main()
