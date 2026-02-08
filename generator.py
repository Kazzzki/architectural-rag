# generator.py - Gemini 3.0 Flash APIで回答生成（Webアプリ版）

from typing import List, Dict, Any, AsyncGenerator

import google.generativeai as genai

from config import GEMINI_MODEL, MAX_TOKENS, TEMPERATURE, GEMINI_API_KEY

# Gemini API設定
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


SYSTEM_PROMPT = """あなたは建築意匠設計の技術アドバイザーです。
建設プロジェクトのPM/CM（プロジェクトマネジメント/コンストラクションマネジメント）の立場から、設計者と技術的な議論ができるレベルで回答してください。

【回答ルール】
1. 技術的根拠を明示する（法令名・基準名・仕様書名を具体的に）
2. コスト・工期・メンテナンスへの影響がある場合は必ず言及する
3. 複数の選択肢がある場合は比較表形式で整理する
4. 知識ベースの情報で回答できない場合は、その旨を正直に伝える
5. 回答の最後に「📎 関連資料」セクションを必ず設ける
6. 日本の建築基準法・JIS・JASS等の日本国内基準に基づく

【出力フォーマット】
回答本文
（Markdown形式、見出し・箇条書き・表を適宜使用）

📎 関連資料:
- [ファイル名]（カテゴリ）
"""


def generate_answer(
    question: str,
    context: str,
    source_files: List[Dict[str, Any]]
) -> str:
    """Gemini 3.0 Flash APIで回答を生成"""
    
    source_files_formatted = "\n".join([
        f"- {file['filename']}（{file['category']}）"
        for file in source_files
    ])
    
    if not context.strip():
        context = "（知識ベースからの検索結果はありませんでした）"
    
    user_prompt = f"""以下の知識ベースの情報を参照して回答してください。

【知識ベースから検索された情報】
{context}

【質問】
{question}

【利用可能な関連ファイル（回答末尾の「📎 関連資料」に含めること）】
{source_files_formatted if source_files_formatted.strip() else "（関連ファイルなし）"}
"""
    
    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config={
                "temperature": TEMPERATURE,
                "max_output_tokens": MAX_TOKENS,
            },
            system_instruction=SYSTEM_PROMPT
        )
        
        response = model.generate_content(user_prompt)
        return response.text
        
    except Exception as e:
        return f"エラーが発生しました: {str(e)}\n\nもう一度お試しください。"


async def generate_answer_stream(
    question: str,
    context: str,
    source_files: List[Dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """ストリーミング形式で回答を生成"""
    
    source_files_formatted = "\n".join([
        f"- {file['filename']}（{file['category']}）"
        for file in source_files
    ])
    
    if not context.strip():
        context = "（知識ベースからの検索結果はありませんでした）"
    
    user_prompt = f"""以下の知識ベースの情報を参照して回答してください。

【知識ベースから検索された情報】
{context}

【質問】
{question}

【利用可能な関連ファイル（回答末尾の「📎 関連資料」に含めること）】
{source_files_formatted if source_files_formatted.strip() else "（関連ファイルなし）"}
"""
    
    try:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config={
                "temperature": TEMPERATURE,
                "max_output_tokens": MAX_TOKENS,
            },
            system_instruction=SYSTEM_PROMPT
        )
        
        response = model.generate_content(user_prompt, stream=True)
        
        for chunk in response:
            if chunk.text:
                yield chunk.text
                
    except Exception as e:
        yield f"エラーが発生しました: {str(e)}"
