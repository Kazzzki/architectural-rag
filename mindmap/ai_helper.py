import asyncio
import json
import logging
import unicodedata
import re
from fastapi import HTTPException
from typing import Dict, Any, Optional, List

# Root directory no gemini_client tsukau
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from gemini_client import get_client

logger = logging.getLogger(__name__)

# --- 多角的技術リサーチ: 専門家ペルソナ定義 ---

RESEARCH_PERSONAS = [
    {
        "id": "legal",
        "name": "法規専門家",
        "icon": "⚖️",
        "description": "建築基準法・消防法・バリアフリー法・各種条例の観点",
        "system_prompt": (
            "あなたは建築法規の専門家です。"
            "建築基準法、消防法、バリアフリー法、各種条例・行政指導の観点から分析してください。"
            "法規上のリスク、確認申請・審査での注意点、適合義務のある基準を中心に述べてください。"
        ),
    },
    {
        "id": "technical",
        "name": "技術エンジニア",
        "icon": "🔧",
        "description": "構造・設備・意匠の技術的工法・品質・施工可能性の観点",
        "system_prompt": (
            "あなたは建築技術の専門家（構造・設備・意匠）です。"
            "工法選定、材料特性、施工精度、品質管理、技術的リスクの観点から分析してください。"
            "実際の施工での課題、設計図への落とし込み時の注意点を中心に述べてください。"
        ),
    },
    {
        "id": "manufacturer",
        "name": "メーカー・調達担当",
        "icon": "📦",
        "description": "製品カタログ・仕様・調達・納期・コストの観点",
        "system_prompt": (
            "あなたはメーカーおよび調達の専門家です。"
            "製品仕様・カタログ上の性能値、代替製品の選択肢、調達リードタイム、"
            "コスト相場、メーカー保証・アフターサービスの観点から分析してください。"
            "特に仕様決定・発注タイミングで見落としがちなポイントを指摘してください。"
        ),
    },
    {
        "id": "pmcm",
        "name": "CMrコンサルタント",
        "icon": "📊",
        "description": "スケジュール・コスト・リスク管理・品質管理の観点",
        "system_prompt": (
            "あなたはCM（コンストラクションマネジメント）の専門家です。"
            "工程管理、コスト管理、リスク管理、品質管理、ステークホルダー調整の観点から分析してください。"
            "特にオーナー利益保護の視点で、判断ミスが起きやすいポイントや"
            "事前に確認すべきことを中心に述べてください。"
        ),
    },
]

_PERSONA_ANALYSIS_SCHEMA = """{
  "key_concerns": ["懸念事項1（簡潔に）", "懸念事項2", "懸念事項3"],
  "critical_checks": ["必ず確認すべき事項1", "必ず確認すべき事項2"],
  "process_steps": ["このペルソナ視点での推奨プロセスステップ1", "ステップ2", "ステップ3"],
  "collaboration_needs": "他のどの専門家と連携が必要か（1〜2文）"
}"""


async def _run_single_persona(
    persona: Dict[str, Any],
    node_content: str,
    project_context: str,
    model_name: str,
) -> Dict[str, Any]:
    """単一ペルソナの分析を実行してJSONを返す"""
    prompt = f"""
{persona['system_prompt']}

【分析対象ノード】
{node_content}

【プロジェクト文脈】
{project_context or '（未設定）'}

以下のJSON形式のみで回答してください（日本語）:
{_PERSONA_ANALYSIS_SCHEMA}
"""
    client = get_client()
    from google.genai import types

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.3,
    )
    try:
        config.thinking_config = types.ThinkingConfig(thinking_budget_tokens=None, thinking_level="minimal")
    except Exception:
        pass

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=prompt,
                config=config,
            ),
            timeout=45,
        )
        raw = response.text.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]
        result = json.loads(raw.strip())
        return {"persona": persona, "result": result}
    except Exception as e:
        logger.warning(f"Persona '{persona['id']}' analysis failed: {e}")
        return {
            "persona": persona,
            "result": {
                "key_concerns": ["（分析エラー）"],
                "critical_checks": [],
                "process_steps": [],
                "collaboration_needs": "",
            },
        }


async def _run_synthesis(
    node_content: str,
    project_context: str,
    persona_results: List[Dict[str, Any]],
    model_name: str,
) -> str:
    """各ペルソナの分析を統合し、議論・最終プロセスをMarkdownで生成する"""
    perspectives_text = ""
    for pr in persona_results:
        p = pr["persona"]
        r = pr["result"]
        perspectives_text += f"\n### {p['icon']} {p['name']}（{p['description']}）\n"
        perspectives_text += f"**主な懸念点:** {', '.join(r.get('key_concerns', []))}\n"
        perspectives_text += f"**必須確認事項:** {', '.join(r.get('critical_checks', []))}\n"
        perspectives_text += f"**推奨プロセス:** {', '.join(r.get('process_steps', []))}\n"
        perspectives_text += f"**連携先:** {r.get('collaboration_needs', '')}\n"

    prompt = f"""
あなたは建築プロジェクトのCMrとして、複数の専門家の意見を統合して最終的なプロセスを設計する役割です。

【分析対象】
{node_content}

【プロジェクト文脈】
{project_context or '（未設定）'}

【各専門家の分析結果】
{perspectives_text}

上記の各専門家の意見を踏まえて、以下の構成でMarkdown形式の技術リサーチレポートを作成してください：

1. **💬 専門家間の議論ポイント**
   - 各専門家が「重要だ」と合意している点（3〜4点）
   - 専門家間で見解が分かれる点・優先順位の違い（2〜3点）
   - 見落とされがちだが重要な盲点（1〜2点）

2. **✅ 統合プロセスチェックリスト**
   カテゴリ別（法規 / 技術 / 調達・仕様 / CMr管理）に整理した確認事項を、
   Markdownチェックリスト形式（- [ ] 項目）で記載。
   各項目には「誰が主担当か」を【法規】【技術】【調達】【CMr】のタグで明示。

3. **⚠️ 最重要リスクと対応策**
   このノードで最もリスクが高い事項を2〜3点、その対応策と共に記載。

日本語で記述してください。
"""
    client = get_client()
    from google.genai import types

    config = types.GenerateContentConfig(temperature=0.4)
    try:
        config.thinking_config = types.ThinkingConfig(thinking_budget_tokens=None, thinking_level="minimal")
    except Exception:
        pass

    response = await asyncio.wait_for(
        asyncio.to_thread(
            client.models.generate_content,
            model=model_name,
            contents=prompt,
            config=config,
        ),
        timeout=60,
    )
    return response.text.strip()


async def run_multi_perspective_research(
    node_content: str,
    project_context: str,
    model_name: str = "gemini-2.5-flash",
) -> str:
    """
    3〜4つの専門家ペルソナが並列分析し、議論・統合プロセスを生成する。
    最終的なMarkdown文字列を返す。
    """
    # Phase 1: 全ペルソナを並列実行
    tasks = [
        _run_single_persona(p, node_content, project_context, model_name)
        for p in RESEARCH_PERSONAS
    ]
    persona_results: List[Dict[str, Any]] = await asyncio.gather(*tasks)

    # Phase 2: 統合・議論・プロセス生成
    synthesis = await _run_synthesis(node_content, project_context, persona_results, model_name)

    # --- Markdown整形 ---
    lines = [f"## 🔍 多角的技術リサーチ: {node_content}\n"]
    lines.append("---\n")
    lines.append("### 👥 各専門家の初期分析\n")

    for pr in persona_results:
        p = pr["persona"]
        r = pr["result"]
        lines.append(f"#### {p['icon']} {p['name']}")
        lines.append(f"*{p['description']}*\n")
        concerns = r.get("key_concerns", [])
        if concerns:
            lines.append("**懸念点:**")
            for c in concerns:
                lines.append(f"- {c}")
        critical = r.get("critical_checks", [])
        if critical:
            lines.append("\n**必須確認:**")
            for c in critical:
                lines.append(f"- ✔ {c}")
        lines.append("")

    lines.append("---\n")
    lines.append(synthesis)

    return "\n".join(lines)

def normalize_text(text: str) -> str:
    """テキストを正規化する（空白除去、小文字化、記号除去等）"""
    if not text:
        return ""
    # Unicode NFKC
    text = unicodedata.normalize('NFKC', text)
    # 英数字 lower
    text = text.lower()
    # 全半角スペース除去
    text = re.sub(r'[\s　]+', '', text)
    # 記号除去
    text = re.sub(r'[^\wぁ-んァ-ヶｱ-ﾝﾞﾟ一-龠]+', '', text)
    return text

async def call_gemini_json(
    prompt: str,
    api_key: Optional[str] = None, # Accept but gemini_client usually handles
    model_name: Optional[str] = None, # Accept as model_name or use default
    model: str = "gemini-2.5-flash",
    max_retries: int = 2,
    timeout_seconds: int = 30 # Task-6: Added timeout
) -> Dict[str, Any]:
    """
    Gemini APIを呼び出し、JSONとして返す共通ヘルパー。
    最大2回リトライ、1秒→3秒のバックオフ、thinking_level="minimal"を適用。
    asyncio.wait_for によるタイムアウト制御付き。
    """
    model_to_use = model_name or model
    client = get_client()

    from google.genai import types

    config_dict = {
        "response_mime_type": "application/json",
        "system_instruction": "You are a helpful assistant.",
        "temperature": 0.2
    }
    
    config = types.GenerateContentConfig(**config_dict)
    
    try:
        config.thinking_config = types.ThinkingConfig(thinking_budget_tokens=None, thinking_level="minimal")
    except Exception:
        pass

    attempt = 0
    delays = [1.0, 3.0]
    last_raw_response = ""

    while attempt <= max_retries:
        try:
            # Task-6: Apply timeout
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=model_to_use,
                    contents=prompt,
                    config=config
                ),
                timeout=timeout_seconds
            )
            last_raw_response = response.text.strip()
            
            # Remove markdown JSON fences if any
            if last_raw_response.startswith("```json"):
                last_raw_response = last_raw_response[7:]
            if last_raw_response.endswith("```"):
                last_raw_response = last_raw_response[:-3]
            last_raw_response = last_raw_response.strip()

            result = json.loads(last_raw_response)
            return result
        except asyncio.TimeoutError:
            logger.error(f"AI Timeout ({timeout_seconds}s) at attempt {attempt}")
            if attempt == max_retries:
                raise HTTPException(status_code=504, detail="AI処理がタイムアウトしました。再試行してください。")
        except json.JSONDecodeError as je:
            if attempt == max_retries:
                logger.error(f"AI JSON Parse Error: {je} Raw: {last_raw_response[:500]}")
                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": "AI応答の解析に失敗しました。再度お試しください",
                        "raw_response": last_raw_response
                    }
                )
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"Gemini API Error details: {e}")
                raise HTTPException(status_code=502, detail=f"AIリクエストが失敗しました: {str(e)}")
        
        # Retry logic with async sleep
        delay_index = attempt if attempt < len(delays) else len(delays) - 1
        await asyncio.sleep(delays[delay_index])
        attempt += 1

    raise HTTPException(
        status_code=502,
        detail={
            "error": "AI応答の解析に失敗しました。再度お試しください",
            "raw_response": last_raw_response
        }
    )
