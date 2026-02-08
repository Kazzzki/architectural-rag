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
        # 1. ルールベース分類
        rule_result = self._rule_based_classify(text, metadata)
        
        # 2. AI分類
        ai_result = self._ai_classify(text, metadata, rule_result)
        
        # 3. 結果の統合と信頼度判定
        final_result = self._merge_results(rule_result, ai_result)
        
        return final_result

    def _rule_based_classify(self, text: str, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """キーワードや正規表現によるルールベース分類"""
        result = {}
        
        # Content Domain
        domain_matches = []
        if 'content_domain' in self.rules:
            for domain_key, subdomains in self.rules['content_domain'].items():
                for subdomain_key, rules in subdomains.items():
                    score = 0
                    # Title keywords (if available in metadata)
                    if metadata and 'title' in metadata:
                        for kw in rules.get('keywords', []):
                            if kw in metadata['title']:
                                score += rules.get('weight_title', 3)
                    
                    # Body keywords
                    for kw in rules.get('keywords', []):
                        if kw in text[:5000]: # Check first 5000 chars
                            score += rules.get('weight_body', 1)
                            
                    # Citations regex
                    for regex in rules.get('citations_regex', []):
                        if re.search(regex, text):
                            score += 3
                            
                    if score >= 4:
                        domain_matches.append(f"{domain_key}/{subdomain_key}")
        
        result['content_domain'] = list(set(domain_matches))
        
        # TODO: Implement other axes if needed for rule-based
        # For now, relying heavily on AI for complex axes, rule-based for domain triggers.
        
        return result

    def _ai_classify(self, text: str, metadata: Optional[Dict[str, Any]], rule_result: Dict[str, Any]) -> Dict[str, Any]:
        """Gemini APIによる分類"""
        try:
            system_prompt = self.rules.get('system_prompt', '')
            user_prompt_template = self.rules.get('user_prompt_template', '')
            
            # コンテキスト作成
            title = metadata.get('title', '不明') if metadata else '不明'
            headings = "" # Extract headings if possible (not implemented yet)
            body_excerpt = text[:2000]
            urls = "" # Extract URLs if possible
            detected_citations = ", ".join(rule_result.get('content_domain', []))
            
            prompt = user_prompt_template.format(
                title=title,
                headings=headings,
                body_excerpt=body_excerpt,
                urls=urls,
                detected_citations=detected_citations
            )
            
            # JSONモードを強制するための設定（Gemini 1.5 Pro/Flash は response_mime_type 対応）
            generation_config = {"response_mime_type": "application/json"}
            
            response = self.model.generate_content(
                [system_prompt, prompt],
                generation_config=generation_config
            )
            
            return json.loads(response.text)
            
        except Exception as e:
            logger.error(f"AI分類エラー: {e}")
            return {}

    def _merge_results(self, rule_result: Dict[str, Any], ai_result: Dict[str, Any]) -> Dict[str, Any]:
        """ルールベースとAIの結果を統合"""
        # 基本的にAIの結果を採用し、ルールベースで検知した確度の高いものを補完する方針
        final = ai_result.copy()
        
        # ルールベースで検出されたドメインが含まれていなければ追加
        current_domains = set(final.get('content_domain', []))
        rule_domains = set(rule_result.get('content_domain', []))
        
        # 信頼度判定ロジック実装（簡易版）
        confidence = final.get('confidence', {})
        
        # ルールベースとAIが一致していれば信頼度High
        overlapping = current_domains.intersection(rule_domains)
        if overlapping:
            confidence['content_domain'] = 'high'
            final['content_domain'] = list(current_domains.union(rule_domains))
        elif rule_domains:
            # ルールベースのみにあるものは追加しておく
            final['content_domain'] = list(current_domains.union(rule_domains))
            if confidence.get('content_domain') == 'high':
                pass # AIが自信満々ならそのまま
            else:
                confidence['content_domain'] = 'medium' # 意見割れ
        
        final['confidence'] = confidence
        return final

    def generate_frontmatter(self, classification_result: Dict[str, Any]) -> str:
        """分類結果からYAML Frontmatterを生成"""
        # 不要なフィールドを除去したり、整形したりする
        data = classification_result.copy()
        
        # YAMLとしてダンプ
        yaml_str = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return f"---\n{yaml_str}---\n"
