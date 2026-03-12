import json

with open("samples/example_plans/building_stats_ops.json", "r") as f:
    plan = json.load(f)

for op in plan:
    if "sheet" not in op:
        # add_sheet needs a sheet name to satisfy the schema or executor
        op["sheet"] = "データベース化"

with open("samples/example_plans/building_stats_ops.json", "w") as f:
    json.dump(plan, f, ensure_ascii=False, indent=2)
