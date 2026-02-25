from fastapi import APIRouter
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Tags & Categories"])

@router.get("/api/categories")
async def list_categories():
    """利用可能なカテゴリ一覧"""
    categories = [
        {"value": None, "label": "全て（横断検索）"},
        {"value": "01_カタログ", "label": "01 カタログ"},
        {"value": "02_図面", "label": "02 図面"},
        {"value": "03_技術基準", "label": "03 技術基準"},
        {"value": "04_リサーチ成果物", "label": "04 リサーチ成果物"},
        {"value": "05_法規", "label": "05 法規"},
        {"value": "06_設計マネジメント", "label": "06 設計マネジメント"},
        {"value": "07_コストマネジメント", "label": "07 コストマネジメント"},
        {"value": "00_未分類", "label": "00 未分類"},
    ]
    return {"categories": categories}

@router.get("/api/tags")
def get_tags():
    """利用可能なタグ一覧を取得"""
    try:
        import yaml
        # server.pyは architectural_rag 直下にいるため base_dir は同じになるように
        base_dir = Path(__file__).parent.parent.resolve()
        rules_path = base_dir / "classification_rules.yaml"
        if not rules_path.exists():
            return {}
            
        with open(rules_path, 'r', encoding='utf-8') as f:
            rules = yaml.safe_load(f)
            
        return rules.get("available_tags", {})
    except Exception as e:
        logger.error(f"Failed to load tags: {e}", exc_info=True)
        return {}
