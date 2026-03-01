from typing import List, Dict, Any

AGGREGATOR_SYSTEM_PROMPT = """あなたは建築プロジェクト管理の上席リサーチャーです。
役割: ノードの事前情報（ギャップ分析）と、検索AIによる各ギャップの調査結果を踏まえて、「何が既に判明し、何がまだ不明か」を明示しながら最終的なリサーチ指示書（ツールプロンプト）と抽出された知識リストを生成することです。

【出力フォーマット】
以下のフォーマットに完全に一致させること（既存のパーサーと互換性を保つため必須）。

---GAP_ANALYSIS---
・（ギャップ1の概要）
・（ギャップ2の概要）
---TOOL_INSTRUCTIONS---
TOOL: Gemini Deep Research
（指示書本文。各調査結果を踏まえ、「検索でXXまでは判明したが、YYの一次情報や具体事例が不足しているため以下を調査せよ」といった形で指示を出すこと。全体で300〜400字程度。）
TOOL: Perplexity Pro
（指示書本文。）
TOOL: Claude web_fetch
（指示書本文。）
---KNOWLEDGE_ITEMS---
ITEM: [タイトル（30字以内）]
TAGS: [関連タグをカンマ区切り、5個程度]
CONTENT: [検索AIの調査結果から抽出・整理できた具体的な知識、基準、法律、実務上の注意点などを記載。150〜200字程度。]
---
---END---
"""

def build_aggregator_prompt(
    node_context: Dict[str, Any],
    search_results: List[Dict[str, Any]],
    selected_tools: List[str]
) -> str:
    prompt = f"""
【対象ノード】
ノード名: {node_context.get('label', '')}
概要: {node_context.get('desc', '')}

【各GAPに対する検索AIの調査結果】
"""
    for res in search_results:
        prompt += f"\n--- GAP: {res['gap_title']} ---\n"
        prompt += f"{res.get('findings', '')}\n"
        
    prompt += f"\n【出力対象ツール指示書（以下のツールのみ出力すること）】\n"
    if selected_tools:
        prompt += "\n".join([f"- {tool}" for tool in selected_tools])
    else:
        prompt += "- (指定なし)"
    
    prompt += "\n\n上記の調査結果を統合し、指定されたフォーマットで最終指示書と抽出された知識（KNOWLEDGE_ITEMS）を出力してください。"
    return prompt
