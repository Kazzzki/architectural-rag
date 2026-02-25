# prompts/research_planner.py - Research Planner用システムプロンプト

RESEARCH_PLANNER_SYSTEM_PROMPT = """RAGシステムの技術リサーチ統括AIとして、以下の出力フォーマットで返答する。

---GAP_ANALYSIS---
（不足知識・改善余地を3〜5項目。各行先頭に「・」）
---TOOL_INSTRUCTIONS---
TOOL: {tool_name}
（そのツール向けリサーチ指示書。300〜400字。構造化プロンプト形式。）
---KNOWLEDGE_ITEMS---
ITEM: [タイトル（30字以内）]
TAGS: [タグをカンマ区切り、5個程度]
CONTENT: [検索クエリに対応する知識本文。150〜200字。]
---
---END---

マークダウン装飾（###, **等）は使わず、プレーンテキストで出力。"""

def build_research_prompt(
    node_id: str,
    node_label: str,
    node_desc: str,
    node_components: list,
    node_domains: list,
    search_category: str,
    doc_type: str,
    selected_tools: list,
    focus: str,
    extra_context: str
) -> str:
    """ユーザーのリクエストから最終的なプロンプトを構築する"""
    
    tools_str = ", ".join(selected_tools) if selected_tools else "指定なし"
    components_str = ", ".join(node_components) if node_components else "指定なし"
    domains_str = ", ".join(node_domains) if node_domains else "指定なし"
    
    prompt = f"""現在の対象ノード情報:
- ノードID: {node_id}
- ノード名: {node_label}
- 概要: {node_desc}
- 関連コンポーネント: {components_str}
- 専門ドメイン: {domains_str}
- 検索カテゴリ: {search_category}
- ドキュメント種別: {doc_type}

使用ツール:
{tools_str}

フォーカス領域:
{focus}

追加コンテキスト:
{extra_context if extra_context else "特になし"}

上記を踏まえ、不足している知識ギャップの分析、使用ツールごとの具体的なリサーチ指示書、およびRAGシステムにそのまま投入するための知識アイテム（チャンク）を生成してください。
"""
    return prompt
