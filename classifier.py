import os
import yaml
import re
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL

# ロガー設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Gemini API設定
genai.configure(api_key=GEMINI_API_KEY)

class DocumentClassifier:
    def __init__(self, rules_path: str = "classification_rules.yaml"):
        self.rules_path = rules_path
        self.rules = self._load_rules()
        self.model = genai.GenerativeModel(GEMINI_MODEL)

    def _load_rules(self) -> Dict[str, Any]:
        """分類ルールをYAMLから読み込む"""
        try:
            # 絶対パス解決
            if not os.path.isabs(self.rules_path):
                base_dir = Path(__file__).parent
                self.rules_path = str(base_dir / self.rules_path)
                
            with open(self.rules_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"ルールの読み込みに失敗しました: {e}")
            return {}

    def classify(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        テキストとメタデータ（ファイル名など）を元に分類を実行する
        """
        # AI分類を実行
        ai_result = self._ai_classify(text, metadata)
        
        # 検証と修正
        validated_result = self._validate_result(ai_result)
        
        return validated_result

    def _ai_classify(self, text: str, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Gemini APIによる分類"""
        try:
            system_prompt_template = self.rules.get('system_prompt', '')
            user_prompt_template = self.rules.get('user_prompt_template', '')
            
            allowed_categories = self.rules.get('allowed_categories', [])
            available_tags = self.rules.get('available_tags', {})
            
            # タグリストを平坦化してプロンプトに埋め込む
            flat_tags = []
            for category, tags in available_tags.items():
                flat_tags.extend(tags)
            
            # システムプロンプトのフォーマット
            system_prompt = system_prompt_template.format(
                allowed_categories=json.dumps(allowed_categories, ensure_ascii=False, indent=2),
                available_tags=json.dumps(flat_tags, ensure_ascii=False, indent=2)
            )
            
            # コンテキスト作成
            title = metadata.get('title', '不明') if metadata else '不明'
            body_excerpt = text[:2000]
            
            prompt = user_prompt_template.format(
                title=title,
                body_excerpt=body_excerpt
            )
            
            # JSONモードを強制するための設定
            generation_config = {"response_mime_type": "application/json"}
            
            response = self.model.generate_content(
                [system_prompt, prompt],
                generation_config=generation_config
            )
            
            return json.loads(response.text)
            
        except Exception as e:
            logger.error(f"AI分類エラー: {e}")
            return {"primary_category": "uploads", "tags": [], "page_mapping": {}}

    def _validate_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """分類結果をルールに基づいて検証・修正"""
        validated = result.copy()
        
        # カテゴリ検証
        validated['primary_category'] = self._validate_category(result.get('primary_category'))
        
        # タグ検証
        validated['tags'] = self._validate_tags(result.get('tags', []))
        
        # page_mappingはそのまま（形式チェックは省略）
        if 'page_mapping' not in validated:
            validated['page_mapping'] = {}
            
        return validated

    def _validate_category(self, category: str) -> str:
        """カテゴリが許可リストにあるか確認"""
        allowed = self.rules.get('allowed_categories', [])
        
        if category in allowed:
            return category
            
        # 部分一致検索（簡易）
        for allowed_cat in allowed:
            if category and category in allowed_cat:
                logger.info(f"カテゴリ修正: {category} -> {allowed_cat}")
                return allowed_cat
                
        logger.warning(f"不正なカテゴリ: {category} -> uploads に変更")
        return "uploads"

    def _validate_tags(self, tags: List[str]) -> List[str]:
        """タグが許可リストにあるか確認"""
        available_tags = self.rules.get('available_tags', {})
        flat_allowed_tags = set()
        for group_tags in available_tags.values():
            flat_allowed_tags.update(group_tags)
            
        valid_tags = []
        for tag in tags:
            if tag in flat_allowed_tags:
                valid_tags.append(tag)
            else:
                logger.warning(f"不正なタグを除外: {tag}")
                
        return valid_tags[:10] # 最大10個

    def generate_frontmatter(self, classification_result: Dict[str, Any]) -> str:
        """分類結果からYAML Frontmatterを生成"""
        # 必要なフィールドのみ抽出
        data = {
            "primary_category": classification_result.get("primary_category", "uploads"),
            "tags": classification_result.get("tags", []),
            "page_mapping": classification_result.get("page_mapping", {})
        }
        
        # YAMLとしてダンプ
        yaml_str = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return f"---\n{yaml_str}---\n"
