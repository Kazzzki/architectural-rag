"""
research_engine/planner.py

4人格（法務・技術・メーカー・施工CM）による多視点ディスカッションで
リサーチプランを生成する。Gemini Flash を使用。

フロー:
  Phase 1: 各人格が独立してリサーチ観点と検索クエリを生成（4並列）
  Phase 2: 他人格の意見を読んで補足・反論クエリを追加（4並列）
  Phase 3: 全意見を統合して最終プランJSON生成（1回）
"""

import asyncio
import json
import logging
import textwrap
from typing import Any

from config import GEMINI_API_KEY, GEMINI_MODEL_FLASH
from gemini_client import get_client

logger = logging.getLogger(__name__)

# ===== 人格定義 =====

PERSONAS: list[dict[str, str]] = [
    {
        "id": "legal",
        "name": "法務専門家",
        "role": (
            "あなたは建設・建築分野の法務専門家です。"
            "建築基準法、消防法、労働安全衛生法、都市計画法、品確法など"
            "法令・条例・告示・技術的助言の観点からリサーチ方針を立案します。"
        ),
        "focus": "法令・規制・行政指導・条例・認定制度・罰則・申請手続き",
    },
    {
        "id": "technical",
        "name": "技術エンジニア",
        "role": (
            "あなたは建築構造・設備の技術エンジニアです。"
            "JIS規格、JASS（建築工事標準仕様書）、各種設計基準、"
            "耐震・耐火・断熱性能、構造計算の観点からリサーチ方針を立案します。"
        ),
        "focus": "技術基準・設計指針・性能規定・試験方法・計算基準・JIS/JAS",
    },
    {
        "id": "manufacturer",
        "name": "メーカー仕様専門家",
        "role": (
            "あなたは建設資材・設備機器のメーカー仕様専門家です。"
            "製品カタログ、施工要領書、認定番号（大臣認定・防火認定等）、"
            "メーカー保証条件、代替品・同等品の観点からリサーチ方針を立案します。"
        ),
        "focus": "製品仕様・カタログ・施工要領・認定番号・保証条件・比較製品",
    },
    {
        "id": "construction_pm",
        "name": "施工・PM管理者",
        "role": (
            "あなたは施工管理・プロジェクトマネジメントの専門家です。"
            "施工事例、品質管理、工程計画、コスト、安全管理、"
            "発注者リスク・トラブル事例の観点からリサーチ方針を立案します。"
        ),
        "focus": "施工事例・品質管理・トラブル防止・コスト・工程・安全管理",
    },
]

# ===== プロンプトテンプレート =====

_PHASE1_TMPL = textwrap.dedent("""\
    {role}

    【リサーチ質問】
    {question}

    あなたの専門領域（{focus}）の観点から、この質問を調査するために必要な
    リサーチ観点と検索クエリを提案してください。

    以下のJSON形式のみで回答（前置き・説明文不要）:
    {{
      "persona": "{persona_id}",
      "key_concerns": ["この観点から重要な論点1", "論点2", "論点3"],
      "search_queries": ["日本語検索クエリ1", "クエリ2", "クエリ3", "クエリ4"],
      "missing_risks": ["他の観点が見落としそうなリスク1", "リスク2"]
    }}
""")

_PHASE2_TMPL = textwrap.dedent("""\
    {role}

    【リサーチ質問】
    {question}

    【他の専門家の意見】
    {other_opinions}

    あなた（{persona_name}）の立場から、上記の他の専門家意見を踏まえて：
    1. 補足すべき追加クエリや観点
    2. 他の専門家が見落としている点への指摘

    以下のJSON形式のみで回答（前置き・説明文不要）:
    {{
      "persona": "{persona_id}",
      "additional_queries": ["追加クエリ1", "クエリ2", "クエリ3"],
      "critique": ["他専門家への指摘1", "指摘2"],
      "synthesis_note": "このリサーチで最も重要な1文"
    }}
""")

_PHASE3_TMPL = textwrap.dedent("""\
    あなたはPM/CM専門の技術リサーチプランナーです。
    4人の専門家（法務・技術・メーカー・施工PM）がディスカッションした結果を統合し、
    包括的なリサーチプランを作成してください。

    【リサーチ質問】
    {question}

    【Phase1: 各専門家の初期意見】
    {phase1_summary}

    【Phase2: ディスカッション・追加意見】
    {phase2_summary}

    以下のJSONスキーマ形式のみで出力（前置き・説明文・Markdownコードブロック不要）:
    {{
      "domain": "architecture | construction | general",
      "categories": [
        {{
          "id": "legal | technical | manufacturer | construction_case | academic",
          "name": "カテゴリ表示名",
          "persona_source": "このカテゴリを主導した人格ID",
          "queries": ["検索クエリ1", "クエリ2", "クエリ3"],
          "priority": 1,
          "trust_target": 0.9
        }}
      ],
      "estimated_sources": 20,
      "key_aspects": ["統合された重要観点1", "観点2", "観点3"],
      "discussion_insights": ["ディスカッションで発見された重要知見1", "知見2"]
    }}
""")


# ===== Gemini Flash 呼び出し =====

def _call_gemini_sync(prompt: str) -> str:
    """同期版 Gemini Flash 呼び出し。asyncio.to_thread でラップして使用。"""
    client = get_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL_FLASH,
        contents=prompt,
    )
    return response.text or ""


async def _call_gemini(prompt: str) -> str:
    """非同期 Gemini Flash 呼び出し。"""
    return await asyncio.to_thread(_call_gemini_sync, prompt)


def _parse_json_safe(raw: str, persona_id: str) -> dict[str, Any]:
    """JSONパース。失敗時は空のフォールバック。"""
    # コードブロックを除去
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Planner: JSON parse failed for persona={persona_id}")
        return {"persona": persona_id, "error": "parse_failed"}


# ===== Phase 関数 =====

async def _phase1_persona(persona: dict, question: str) -> dict[str, Any]:
    """Phase1: 各人格が独立してリサーチ観点を生成。"""
    prompt = _PHASE1_TMPL.format(
        role=persona["role"],
        question=question,
        focus=persona["focus"],
        persona_id=persona["id"],
        persona_name=persona["name"],
    )
    raw = await _call_gemini(prompt)
    result = _parse_json_safe(raw, persona["id"])
    logger.info(f"Planner Phase1: {persona['name']} done")
    return result


async def _phase2_persona(
    persona: dict, question: str, phase1_results: list[dict]
) -> dict[str, Any]:
    """Phase2: 他人格の意見を踏まえて補足・反論クエリを生成。"""
    # 自分以外の意見をまとめる
    others = [
        r for r in phase1_results if r.get("persona") != persona["id"]
    ]
    other_text_parts = []
    for r in others:
        pid = r.get("persona", "unknown")
        p_name = next((p["name"] for p in PERSONAS if p["id"] == pid), pid)
        concerns = "\n".join(f"  - {c}" for c in r.get("key_concerns", []))
        queries = "\n".join(f"  - {q}" for q in r.get("search_queries", []))
        other_text_parts.append(
            f"▼ {p_name}\n"
            f"  重要論点:\n{concerns}\n"
            f"  提案クエリ:\n{queries}"
        )
    other_opinions = "\n\n".join(other_text_parts) if other_text_parts else "（なし）"

    prompt = _PHASE2_TMPL.format(
        role=persona["role"],
        question=question,
        other_opinions=other_opinions,
        persona_id=persona["id"],
        persona_name=persona["name"],
    )
    raw = await _call_gemini(prompt)
    result = _parse_json_safe(raw, persona["id"])
    logger.info(f"Planner Phase2: {persona['name']} done")
    return result


async def _phase3_synthesize(
    question: str,
    phase1_results: list[dict],
    phase2_results: list[dict],
) -> dict[str, Any]:
    """Phase3: 全人格の意見を統合して最終プランJSONを生成。"""

    def _summarize_phase(results: list[dict], phase_num: int) -> str:
        parts = []
        for r in results:
            pid = r.get("persona", "unknown")
            p_name = next((p["name"] for p in PERSONAS if p["id"] == pid), pid)
            parts.append(f"[{p_name}] {json.dumps(r, ensure_ascii=False)}")
        return "\n".join(parts)

    phase1_summary = _summarize_phase(phase1_results, 1)
    phase2_summary = _summarize_phase(phase2_results, 2)

    prompt = _PHASE3_TMPL.format(
        question=question,
        phase1_summary=phase1_summary,
        phase2_summary=phase2_summary,
    )
    raw = await _call_gemini(prompt)
    result = _parse_json_safe(raw, "synthesizer")

    # フォールバック: パース失敗時のデフォルト構造
    if "categories" not in result:
        logger.warning("Planner Phase3: synthesis failed, building fallback plan")
        result = _build_fallback_plan(question, phase1_results, phase2_results)

    logger.info("Planner Phase3: synthesis done")
    return result


def _build_fallback_plan(
    question: str,
    phase1_results: list[dict],
    phase2_results: list[dict],
) -> dict[str, Any]:
    """Phase3パース失敗時のフォールバックプラン構築。"""
    all_queries: list[str] = []
    for r in phase1_results:
        all_queries.extend(r.get("search_queries", []))
    for r in phase2_results:
        all_queries.extend(r.get("additional_queries", []))

    return {
        "domain": "construction",
        "categories": [
            {
                "id": "legal",
                "name": "法令・規制",
                "persona_source": "legal",
                "queries": all_queries[:3],
                "priority": 1,
                "trust_target": 0.9,
            },
            {
                "id": "technical",
                "name": "技術基準",
                "persona_source": "technical",
                "queries": all_queries[3:6],
                "priority": 2,
                "trust_target": 0.8,
            },
            {
                "id": "manufacturer",
                "name": "メーカー仕様",
                "persona_source": "manufacturer",
                "queries": all_queries[6:9],
                "priority": 3,
                "trust_target": 0.7,
            },
            {
                "id": "construction_case",
                "name": "施工事例",
                "persona_source": "construction_pm",
                "queries": all_queries[9:12],
                "priority": 4,
                "trust_target": 0.7,
            },
        ],
        "estimated_sources": 20,
        "key_aspects": [question],
        "discussion_insights": [],
    }


# ===== メインエントリーポイント =====

async def generate_plan(question: str) -> dict[str, Any]:
    """
    4人格ディスカッション方式でリサーチプランを生成する。

    Phase1: 各人格が独立してリサーチ観点を生成（4並列）
    Phase2: 他人格の意見を踏まえて補足・反論クエリを追加（4並列）
    Phase3: 全意見を統合して最終プランJSONを生成（1回）
    """
    logger.info(f"Planner: starting multi-persona plan generation for: {question[:60]}")

    # Phase1: 全人格を並列実行
    phase1_results = await asyncio.gather(
        *[_phase1_persona(p, question) for p in PERSONAS],
        return_exceptions=True,
    )
    # 例外をフィルタ
    phase1_results = [
        r if isinstance(r, dict) else {"persona": PERSONAS[i]["id"], "error": str(r)}
        for i, r in enumerate(phase1_results)
    ]
    logger.info("Planner: Phase1 complete")

    # Phase2: 全人格を並列実行（他人格のPhase1結果を参照）
    phase2_results = await asyncio.gather(
        *[_phase2_persona(p, question, phase1_results) for p in PERSONAS],
        return_exceptions=True,
    )
    phase2_results = [
        r if isinstance(r, dict) else {"persona": PERSONAS[i]["id"], "error": str(r)}
        for i, r in enumerate(phase2_results)
    ]
    logger.info("Planner: Phase2 complete")

    # Phase3: 統合
    plan = await _phase3_synthesize(question, phase1_results, phase2_results)

    # メタ情報を付加
    plan["_meta"] = {
        "planner_version": "multi_persona_v1",
        "personas_used": [p["id"] for p in PERSONAS],
        "phase1_count": len([r for r in phase1_results if "error" not in r]),
        "phase2_count": len([r for r in phase2_results if "error" not in r]),
    }

    logger.info("Planner: multi-persona plan generation complete")
    return plan
