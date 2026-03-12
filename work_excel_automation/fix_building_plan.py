import json

with open("samples/example_plans/building_stats_ops.json", "r") as f:
    plan = json.load(f)

plan.insert(0, {
    "op": "add_sheet",
    "params": {"sheet_name": "データベース化"},
    "reason": "集計用シートの作成"
})

with open("samples/example_plans/building_stats_ops.json", "w") as f:
    json.dump(plan, f, ensure_ascii=False, indent=2)
