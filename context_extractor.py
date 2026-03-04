import json
import logging
from gemini_client import get_client
from config import GEMINI_MODEL_RAG

from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


def extract_personal_context(user_message: str, assistant_response: str) -> Optional[List[dict]]:
    """
    会話ペアを分析し、個人知見が含まれるか判定して構造化して返す。

    ステップ1: 判定（個人知見が含まれるか？）
      含まれない → None を返してAPI呼び出し終了（コスト最小化）
      含まれる  → ステップ2へ

    ステップ2: 抽出・構造化
    """
    try:
        client = get_client()

        # Step 1: 判定
        check_prompt = f"""
以下のユーザーとAIの会話に、ユーザーの個人的な知見（判断基準、失敗の学び、気づき）が含まれているか判定してください。

【判定基準】
✅ 抽出する対象：
  - 「〜と判断した」「〜すべき」「〜が重要」
  - 「以前〜で失敗した」「〜の教訓」
  - 「気をつけること」「ポイントは」

❌ 抽出しない対象：
  - 単なる質問だけで個人見解がない
  - 一般的な技術情報の確認
  - 「ありがとう」等の短いやり取り

含まれている場合は "YES"、含まれていない場合は "NO" とだけ回答してください。

[ユーザー]: {user_message}
[AI]: {assistant_response}
"""
        response_check = client.models.generate_content(model=GEMINI_MODEL_RAG, contents=check_prompt)
        check_result = response_check.text.strip().upper()
        if "YES" not in check_result:
            return None

        # Step 2: 抽出・構造化
        extract_prompt = f"""
以下のユーザーとAIの会話から、ユーザーの個人的な知見（判断基準、失敗の学び、気づき）を抽出し、JSON形式で出力してください。

【出力JSON形式】
[
  {{
    "type": "judgement" | "lesson" | "insight",
    "content": "知見の要約（100文字以内・主語なし・体言止め推奨）",
    "trigger_keywords": ["関連キーワード1", "関連キーワード2"],
    "project_tag": "プロジェクト名" (なければnull)
  }}
]

【type の定義】
- judgement：「こういう時はこう判断する」という基準・方針
- lesson：過去の失敗・反省・繰り返さないための記録
- insight：現場での気づき・ヒント・覚えておきたいこと

[ユーザー]: {user_message}
[AI]: {assistant_response}

JSONブロック（```json ... ```）のみを出力してください。
"""
        response_extract = client.models.generate_content(model=GEMINI_MODEL_RAG, contents=extract_prompt)
        text = response_extract.text
        
        # Extract JSON from markdown code block
        if "```json" in text:
            json_str = text.split("```json")[-1].split("```")[0].strip()
        elif "```" in text:
            json_str = text.split("```")[-1].split("```")[0].strip()
        else:
            json_str = text.strip()
            
        candidates = json.loads(json_str)
        if isinstance(candidates, dict):
            # 1件のdictの場合はリストで包む
            candidates = [candidates]
        return candidates

    except Exception as e:
        logger.error(f"Error in extract_personal_context: {e}")
        return None
