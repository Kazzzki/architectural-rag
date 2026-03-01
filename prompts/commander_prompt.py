import json
from typing import List

COMMANDER_SYSTEM_PROMPT = """あなたは建築RAGシステムの知識戦略アナリストです。
役割: 与えられたノードの情報（設計やプロジェクト管理上のフェーズ・課題・検討事項）を精査し、「このノードで意思決定をするために必要だが、現在のRAGに存在していない知識は何か」を特定することです。
表面的なキーワードの不足を指摘するのではなく、「根拠となるどのような情報の欠如がどのような判断ミスを引き起こすか」を掘り下げてください。

【出力形式】
JSONのみを出力してください（Markdownの ```json ... ``` 等の装飾も一切禁止します）。
ギャップは最も重要なものに絞り、3〜5件としてください。

{
  "gaps": [
    {
      "id": "gap_1",
      "title": "ギャップのタイトル（20字以内）",
      "description": "なぜこの情報が必要か・欠如するとどんな判断ミスが起きるか（100字程度）",
      "search_query": "このギャップを解消するための最適な検索クエリテキスト（そのまま検索AIに渡すので、具体的かつ日本語の検索ワードにしてください。例: 建築基準法 第〇条 防火区画 最新 緩和措置）",
      "domain": "law|spec|drawing|cost|process|other"
    }
  ]
}
"""

def build_commander_prompt(
    node_id: str,
    node_label: str,
    node_phase: str,
    node_category: str,
    node_description: str,
    node_checklist: List[str],
    node_deliverables: List[str],
    focus: str,
    extra_context: str
) -> str:
    prompt = f"""
【分析対象ノード情報】
- ノードID: {node_id}
- ノード名: {node_label}
- フェーズ: {node_phase}
- カテゴリ: {node_category}
- 概要: {node_description}
"""
    if node_checklist:
        prompt += f"- チェックリスト: {', '.join(node_checklist)}\n"
    if node_deliverables:
        prompt += f"- 成果物: {', '.join(node_deliverables)}\n"
        
    prompt += "\n"
    if focus:
        prompt += f"【重要フォーカス】\n{focus}\n\n"
        
    if extra_context:
        prompt += f"【追加コンテキスト】\n{extra_context}\n\n"
        
    prompt += "上記のノード情報に対して、不足している知識のギャップを3〜5件抽出し、JSONで出力してください。"
    return prompt
