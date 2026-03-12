import os
import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from core.intake import intake
from core.discovery import discover
from core.profile_matcher import match_profile
from core.planner import build_plan, load_plan
from core.dry_run import dry_run
from core.executor import execute
from core.verifier import verify

mcp = FastMCP("ExcelFlow-HighLevel")

def get_base_dir():
    return os.getcwd()

# Pre-defined dirs for MCP
DIRS = {
    "inbox": os.path.join(get_base_dir(), "data", "inbox"),
    "working": os.path.join(get_base_dir(), "data", "working"),
    "output": os.path.join(get_base_dir(), "data", "output"),
    "plans": os.path.join(get_base_dir(), "data", "plans"),
    "logs": os.path.join(get_base_dir(), "data", "logs"),
    "profiles": os.path.join(get_base_dir(), "profiles")
}

for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

@mcp.tool()
def discover_workbook(file_path: str) -> str:
    """Discover the structure of an Excel workbook (Intake + Discover)."""
    try:
        res = intake(file_path, DIRS["working"])
        summary = discover(res.working_path)
        out = {
            "run_id": res.run_id,
            "working_path": res.working_path,
            "summary": summary.to_dict()
        }
        return json.dumps(out, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def match_workbook_profile(working_path: str) -> str:
    """Match a discovered workbook against standard profiles."""
    try:
        summary = discover(working_path)
        match_res = match_profile(summary, DIRS["profiles"])
        return json.dumps({
            "matched_profile_id": match_res.matched_profile_id,
            "score": match_res.score,
            "reason": match_res.reason
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def generate_plan(run_id: str, input_file: str, working_path: str, profile_id: str, operations_json: str) -> str:
    """Generate an execution plan based on specific operations."""
    try:
        summary = discover(working_path)
        # Mocking match result based on input
        from core.models import MatchResult
        match_res = MatchResult(matched_profile_id=profile_id, score=1.0, reason="Manual assignment via MCP", is_fallback=False)
        
        ops = json.loads(operations_json)
        plan = build_plan(run_id, input_file, "AUTO", summary, match_res, ops, DIRS["plans"])
        return json.dumps({"plan_path": os.path.join(DIRS["plans"], f"{Path(input_file).stem}__plan_{run_id}.json"), "plan": plan.to_dict()}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def dry_run_plan(plan_path: str, working_path: str) -> str:
    """Dry run an execution plan to check safety and preconditions."""
    try:
        plan = load_plan(plan_path)
        summary = discover(working_path)
        report = dry_run(plan, summary)
        return json.dumps(report.to_dict(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def execute_plan(plan_path: str, working_path: str) -> str:
    """Execute a validated plan."""
    try:
        plan = load_plan(plan_path)
        exec_res = execute(plan, working_path, DIRS["output"], DIRS["logs"])
        return json.dumps(exec_res.to_dict(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def verify_run(plan_path: str, working_path: str, output_path: str) -> str:
    """Verify the result of an executed plan."""
    try:
        plan = load_plan(plan_path)
        report = verify(plan, working_path, output_path, DIRS["logs"])
        return json.dumps(report.to_dict(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    mcp.run()
