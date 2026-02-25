import os
import re
import json
import argparse

def parse_markdown_to_mindmap(filepath: str) -> dict:
    """
    指定されたMarkdownファイルをパースし、マインドマップ用の階層型JSONデータを生成します。
    """
    if not os.path.exists(filepath):
        print(f"Error: File not found {filepath}")
        return None
        
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # Root Node
    root_node = {
        "name": "企画構想フェーズ：意思決定の依存関係分析",
        "children": []
    }
    
    current_section = None
    current_section_node = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 見出し（セクション）の検知: 例 ## 【1. 多対1の依存】
        header_match = re.match(r'^##\s+【(.+?)】', line)
        if header_match:
            current_section = header_match.group(1)
            current_section_node = {
                "name": current_section,
                "children": []
            }
            root_node["children"].append(current_section_node)
            continue
            
        # テーブル行の検知とパース
        if current_section and line.startswith('|'):
            # 区切り線はスキップ
            if '---' in line:
                continue
                
            # カラムごとの分割とクリーンアップ
            cols = [c.strip() for c in line.strip('|').split('|')]
            
            # ヘッダー行をスキップ
            if not cols or cols[0] == '#' or cols[0] == 'カテゴリ' or cols[0].startswith('---'):
                continue
                
            try:
                # 【1. 多対1の依存】
                if current_section.startswith('1.'):
                    # | # | 入力A | AND 入力B | AND 入力C | → 決定可能な事項D |
                    if len(cols) >= 5:
                        d_col = cols[4]
                        parent = {"name": d_col, "children": []}
                        if cols[1] and cols[1] != '-': parent["children"].append({"name": f"入力A: {cols[1]}"})
                        if cols[2] and cols[2] != '-': parent["children"].append({"name": f"入力B: {cols[2]}"})
                        if cols[3] and cols[3] != '-': parent["children"].append({"name": f"入力C: {cols[3]}"})
                        if parent["children"]: # 子がいる場合のみ追加
                            current_section_node["children"].append(parent)
                        
                # 【2. フィードバックループ】
                elif current_section.startswith('2.'):
                    # | # | D決定 | → 後工程Eの情報 | → D再検討が必要なケース |
                    if len(cols) >= 4:
                        d_col = cols[1]
                        parent = {"name": d_col, "children": []}
                        if cols[2] and cols[2] != '-': parent["children"].append({"name": f"後工程情報: {cols[2]}"})
                        if cols[3] and cols[3] != '-': parent["children"].append({"name": f"再検討ケース: {cols[3]}"})
                        if parent["children"]:
                            current_section_node["children"].append(parent)
                        
                # 【3. 仮決め進行の条件とリスク】
                elif current_section.startswith('3.'):
                    # | # | 仮定 | 条件（成立する場合のみ有効） | 外れた場合の影響 |
                    if len(cols) >= 4:
                        katei = cols[1]
                        parent = {"name": katei, "children": []}
                        if cols[2] and cols[2] != '-': parent["children"].append({"name": f"条件: {cols[2]}"})
                        if cols[3] and cols[3] != '-': parent["children"].append({"name": f"外れた影響: {cols[3]}"})
                        if parent["children"]:
                            current_section_node["children"].append(parent)
                        
                # 【4. クリティカルパス】
                elif current_section.startswith('4.'):
                    # | # | 決定事項 | 影響を受ける後続 | 最遅期限 |
                    if len(cols) >= 4:
                        kettei = cols[1]
                        parent = {"name": kettei, "children": []}
                        if cols[2] and cols[2] != '-': parent["children"].append({"name": f"影響有(後続): {cols[2]}"})
                        if cols[3] and cols[3] != '-': parent["children"].append({"name": f"最遅期限: {cols[3]}"})
                        if parent["children"]:
                            current_section_node["children"].append(parent)
                        
                # 【5. 担当者間の情報断絶リスク】
                elif current_section.startswith('5.'):
                    # | # | 送り手 | 受け手 | 伝達すべき情報 | 未伝達時のリスク |
                    if len(cols) >= 5:
                        jouhou = cols[3]
                        parent = {"name": jouhou, "children": []}
                        if cols[1] and cols[1] != '-': parent["children"].append({"name": f"送り手: {cols[1]}"})
                        if cols[2] and cols[2] != '-': parent["children"].append({"name": f"受け手: {cols[2]}"})
                        if cols[4] and cols[4] != '-': parent["children"].append({"name": f"未伝達リスク: {cols[4]}"})
                        if parent["children"]:
                            current_section_node["children"].append(parent)
                        
                # 【6. 暗黙の前提条件】
                elif current_section.startswith('6.'):
                    # | カテゴリ | 前提条件 | 前提が崩れた場合 |
                    if len(cols) >= 3:
                        zentei = cols[1]
                        parent = {"name": zentei, "children": []}
                        if cols[0] and cols[0] != '-': parent["children"].append({"name": f"カテゴリ: {cols[0]}"})
                        if cols[2] and cols[2] != '-': parent["children"].append({"name": f"前提崩壊リスク: {cols[2]}"})
                        if parent["children"]:
                            current_section_node["children"].append(parent)
                            
            except Exception as e:
                # エラーが起きても全体を止めないようにエラーハンドリング
                print(f"Warning: Failed to parse row in [{current_section}]: {line}. Error: {e}")
                pass
                
    return root_node

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse markdown table to mindmap hierarchical JSON")
    parser.add_argument("input_file", help="Path to markdown file")
    parser.add_argument("--output", "-o", default="mindmap_data.json", help="Output JSON file path")
    args = parser.parse_args()
    
    data = parse_markdown_to_mindmap(args.input_file)
    if data:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Successfully exported hierarchical JSON to {args.output}")
