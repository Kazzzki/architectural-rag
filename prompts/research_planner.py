# prompts/research_planner.py - Research Planner用システムプロンプト

RESEARCH_PLANNER_SYSTEM_PROMPT = """あなたは建築PM/CM業務の技術リサーチ統括AIです。
設計プロセスの特定ノード（業務フェーズ）について、
実務で必要な知識の強化リサーチ計画を立案します。

## 出力フォーマット（必ずこの構造で返答）
---GAP_ANALYSIS---
（このノードで不足している可能性がある知識・情報を3〜5項目。各行先頭に「・」）
---TOOL_INSTRUCTIONS---
TOOL: [ツール名]
（そのツール向けリサーチ指示書。300〜400字。構造化プロンプト形式。）
TOOL: [次のツール名]
（指示書）
---KNOWLEDGE_ITEMS---
ITEM: [タイトル（30字以内）]
TAGS: [タグをカンマ区切り、5個程度]
CONTENT: [このノードの検索クエリに対応する知識本文。150〜200字。]
---
---END---

マークダウン装飾（###, **等）は使わずプレーンテキストで出力。"""

def build_research_prompt(
    node_id: str,
    node_label: str,
    node_phase: str,
    node_category: str,
    node_description: str,
    node_checklist: list,
    node_deliverables: list,
    selected_tools: list,
    focus: str,
    extra_context: str
) -> str:
    """ユーザーのリクエストから最終的なプロンプトを構築する"""
    
    tools_str = ", ".join(selected_tools) if selected_tools else "指定なし"
    checklist_str = "\n".join([f"- {item}" for item in node_checklist]) if node_checklist else "指定なし"
    deliverables_str = "\n".join([f"- {item}" for item in node_deliverables]) if node_deliverables else "指定なし"
    
    prompt = f"""現在の対象ノード情報:
- ノードID: {node_id}
- ノード名: {node_label}
- 業務フェーズ: {node_phase}
- カテゴリ: {node_category}
- 概要: {node_description}

【確認チェックリスト】
{checklist_str}

【成果物】
{deliverables_str}

使用ツール:
{tools_str}

フォーカス領域:
{focus if focus else "特になし"}

追加コンテキスト:
{extra_context if extra_context else "特になし"}

上記を踏まえ、不足している知識ギャップの分析、使用ツールごとの具体的なリサーチ指示書、およびRAGシステムにそのまま投入するための知識アイテム（チャンク）を生成してください。
"""
    return prompt
