import time
import json
import logging
import unicodedata
import re
from fastapi import HTTPException
from typing import Dict, Any, Optional

# Root directory no gemini_client tsukau
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from gemini_client import get_client

logger = logging.getLogger(__name__)

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

def call_gemini_json(
    prompt: str,
    model: str = "gemini-2.5-flash",
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    Gemini APIを呼び出し、JSONとして返す共通ヘルパー。
    最大2回リトライ、1秒→3秒のバックオフ、thinking_level="minimal"を適用。
    """
    client = get_client()

    from google.genai import types

    # thinking_level は GenerateContentConfig がサポートしている想定。
    # エラー時は無視するか、SDKバージョンに合わせて調整。
    config_dict = {
        "response_mime_type": "application/json",
        "system_instruction": "You are a helpful assistant.", # Default prompt
        "temperature": 0.2
    }
    
    config = types.GenerateContentConfig(**config_dict)
    
    # 5. `thinking_level="minimal"` 固定
    # Depending on SDK, could be object property or kwargs.
    try:
        config.thinking_config = types.ThinkingConfig(thinking_budget_tokens=None, thinking_level="minimal")
    except Exception:
        # Some SDK versions might not support thinking_config directly, ignore if not possible
        pass

    attempt = 0
    delays = [1.0, 3.0]
    
    last_raw_response = ""

    while attempt <= max_retries:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
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
        
        # Retry logic
        delay_index = attempt if attempt < len(delays) else len(delays) - 1
        time.sleep(delays[delay_index])
        attempt += 1

    # Safe fallback although loop covers it
    raise HTTPException(
        status_code=502,
        detail={
            "error": "AI応答の解析に失敗しました。再度お試しください",
            "raw_response": last_raw_response
        }
    )
