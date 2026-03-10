import json
import logging
import datetime
from typing import List, Dict, Any
from gemini_client import get_client
from config import GEMINI_MODEL_RAG
from database import find_similar_contexts, insert_context, merge_context, invalidate_context

logger = logging.getLogger(__name__)

def update_contexts_with_dedup(candidates: List[Dict[str, Any]], source_question: str, project_id: str = None) -> None:
    """
    Mem0のPhase 2に準拠した更新処理。
    各候補に対して以下を実行：
    Step 1: 類似エントリ検索
    Step 2: LLMによる4択判定
    Step 3: 判定結果に応じてDB操作
    """
    if not candidates:
        return

    try:
        client = get_client()
    except Exception as e:
        logger.error(f"Cannot get Gemini client for dedup: {e}")
        client = None

    for candidate in candidates:
        candidate["source_question"] = source_question
        candidate["project_id"] = project_id
        keywords = candidate.get("trigger_keywords", [])
        
        # Step 1: 類似エントリ検索
        similar_contexts = []
        if keywords:
            try:
                similar_contexts = find_similar_contexts(keywords, limit=5)
            except Exception as e:
                logger.error(f"Error finding similar contexts: {e}")
                
        # 類似エントリが0件 -> 即ADD
        if not similar_contexts or not client:
            if not similar_contexts:
                logger.info("No similar contexts found. Adding new context directly.")
            else:
                logger.info("Gemini client unavailable. Adding new context directly.")
            insert_context(candidate)
            continue

        # Step 2: LLMによる4択判定
        existing_list = [
            {
                "id": ctx.id,
                "content": ctx.content,
                "type": ctx.type
            }
            for ctx in similar_contexts
        ]

        prompt = f"""
新しい個人的な知見（候補）と既存の知見一覧を比較し、これらが重複・矛盾していないか判定してください。
以下のいずれかのアクションを選んでJSON形式で返してください：

- ADD       : 独立した新しい知見。既存とは別に保存すべき。
- MERGE     : 既存の知見と同トピックだが、より詳細または最新。既存を更新する。
- SKIP      : 既存と実質的に同じ内容。保存不要。
- INVALIDATE: 新しい知見が既存を否定・覆している。既存を無効化して新規保存。

【新しい知見】
{json.dumps(candidate, ensure_ascii=False, indent=2)}

【既存の知見一覧】
{json.dumps(existing_list, ensure_ascii=False, indent=2)}

【返り値形式】
JSONブロック（```json ... ```）のみを出力してください：
{{
  "decision": "ADD" | "MERGE" | "SKIP" | "INVALIDATE",
  "target_id": 対象となる既存のID（該当なしの場合はnull）,
  "merged_content": MERGEの場合の統合後テキスト（それ以外はnull。100文字以内で主語なしを推奨）
}}
"""
        
        decision_data = {"decision": "ADD", "target_id": None, "merged_content": None}
        try:
            response = client.models.generate_content(model=GEMINI_MODEL_RAG, contents=prompt)
            text = response.text
            
            if "```json" in text:
                json_str = text.split("```json")[-1].split("```")[0].strip()
            elif "```" in text:
                json_str = text.split("```")[-1].split("```")[0].strip()
            else:
                json_str = text.strip()
                
            parsed = json.loads(json_str)
            decision_data.update(parsed)
            
        except Exception as e:
            logger.warning(f"Error parsing LLM decision for dedup, defaulting to ADD: {e}")
            decision_data["decision"] = "ADD"

        decision = decision_data.get("decision", "ADD")
        target_id = decision_data.get("target_id")
        merged_content = decision_data.get("merged_content")

        logger.info(f"Dedup decision: {decision} for candidate type {candidate.get('type')} (target_id: {target_id})")

        # Step 3: 判定結果に応じてDB操作
        try:
            if decision == "SKIP":
                logger.debug(f"Skipping duplicate context, target_id={target_id}")
                pass
                
            elif decision == "MERGE" and target_id is not None and merged_content:
                now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                merge_log = {
                    "merged_at": now_str,
                    "original": candidate.get("content"),
                    "source_question": source_question
                }
                merge_context(target_id, merged_content, merge_log)
                
            elif decision == "INVALIDATE" and target_id is not None:
                invalidate_context(target_id)
                insert_context(candidate)
                
            else:
                # ADD or fallback
                insert_context(candidate)
                
        except Exception as e:
            logger.error(f"Error saving context (decision: {decision}): {e}")
            # エラー時は念のためADDだけ試す
            try:
                if decision != "ADD":
                    logger.info("Falling back to ADD...")
                    insert_context(candidate)
            except Exception as inner_e:
                logger.error(f"Fallback ADD failed: {inner_e}")
