import json
import os
from adapters.excel_adapter import ExcelAdapter

def process_file():
    in_file = "/Users/kkk/Dropbox (個人用)/My Mac (kkkのMac mini)/Downloads/建築着工統計による単価の推移 のコピー (2).xlsx"
    adapter = ExcelAdapter(in_file)
    
    sheets = ['鉄骨鉄筋コンクリート造', '鉄筋コンクリート造', '鉄骨造']
    
    db_data = [["構造", "用途", "時期", "床面積の合計（㎡）", "工事費予定額（万円）", "面積単価（万円/㎡）", "面積単価（万円/坪）"]]
    
    for sh in sheets:
        raw = adapter.read_range(sh, min_row=3, max_row=40, min_col=2, max_col=300)
        if not raw or len(raw) < 2:
            continue
            
        # Row 0 is Period (column 1, 5, 9, 13...)
        # Row 1 is Metrics header
        # Row 2+ is Usage kind
        
        periods = raw[0]
        metrics = raw[1]
        
        # Col 0 is usage kind
        for r_idx in range(2, len(raw)):
            row = raw[r_idx]
            usage = row[0]
            if not usage:
                continue
                
            # Iterate through periods (step = 4)
            for c_idx in range(1, len(row), 4):
                period = periods[c_idx] if c_idx < len(periods) and periods[c_idx] is not None else None
                if not period:
                    # try to seek left if merged (often it's on the first col of the group)
                    # let's just remember the last seen period
                    pass
                
                # We need to trace the period properly due to merged cells
                current_period = None
                for scan_c in range(c_idx, 0, -1):
                    if scan_c < len(periods) and periods[scan_c] is not None:
                        current_period = periods[scan_c]
                        break
                
                if current_period is None:
                    continue
                
                area = row[c_idx] if c_idx < len(row) else None
                cost = row[c_idx+1] if c_idx+1 < len(row) else None
                sqm = row[c_idx+2] if c_idx+2 < len(row) else None
                tsubo = row[c_idx+3] if c_idx+3 < len(row) else None
                
                if area is None and cost is None and sqm is None and tsubo is None:
                    continue # empty cell block
                    
                db_data.append([sh, usage, current_period, area, cost, sqm, tsubo])
    
    plan = [
        {
            "op": "write_range",
            "sheet": "データベース化",
            "params": {
                "start_row": 1,
                "start_col": 1,
                "data": db_data
            },
            "reason": "3つのシートの統計データを一元化"
        }
    ]
    
    with open("samples/example_plans/building_stats_ops.json", "w") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        
process_file()
