"""
API設定の保存・読み込みモジュール
Web UIからAPI keyやモデルを設定可能にする
"""
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# 設定ファイルパス
SETTINGS_FILE = Path(__file__).parent / "data" / "api_settings.json"

# デフォルト設定
DEFAULT_SETTINGS = {
    "gemini_api_key": "",
    "analysis_model": "gemini-3-flash-preview",
    "available_models": [
        "gemini-3-flash-preview",
        "gemini-3-pro-preview",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ],
}


def _ensure_dir():
    """設定ファイルのディレクトリを作成"""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_settings() -> Dict[str, Any]:
    """設定を読み込む（ファイル → .env フォールバック）"""
    settings = dict(DEFAULT_SETTINGS)
    
    # ファイルから読み込み
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            settings.update(saved)
        except Exception as e:
            logger.warning(f"Settings load error: {e}")
    
    # APIキーが未設定の場合、.envからフォールバック
    if not settings.get("gemini_api_key"):
        env_key = os.environ.get("GEMINI_API_KEY", "")
        if env_key:
            settings["gemini_api_key"] = env_key
    
    return settings


def save_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    """設定を保存"""
    _ensure_dir()
    
    # 既存設定を読み込み
    current = load_settings()
    
    # 更新可能なフィールドのみ適用
    allowed_fields = {"gemini_api_key", "analysis_model"}
    for key, value in updates.items():
        if key in allowed_fields:
            current[key] = value
    
    # ファイルに保存（available_modelsは保存しない）
    save_data = {k: v for k, v in current.items() if k != "available_models"}
    
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"API settings saved")
    
    # available_modelsを含めて返す
    current["available_models"] = DEFAULT_SETTINGS["available_models"]
    return current


def get_api_key() -> str:
    """現在有効なAPIキーを取得"""
    settings = load_settings()
    return settings.get("gemini_api_key", "")


def get_analysis_model() -> str:
    """現在の分析モデルを取得"""
    settings = load_settings()
    return settings.get("analysis_model", DEFAULT_SETTINGS["analysis_model"])
