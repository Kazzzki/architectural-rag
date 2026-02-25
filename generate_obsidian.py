import google.generativeai as genai
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. APIキーとモデルの設定
# ==========================================
# ターミナルで export GEMINI_API_KEY="あなたのキー" を実行しておくか、直接入力してください
API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY 環境変数が設定されていません。export GEMINI_API_KEY='あなたのキー' を実行してください。")
genai.configure(api_key=API_KEY)

# 思考を広げる用（生成・批判フェーズ）
model_text = genai.GenerativeModel(
    model_name="gemini-3-flash-preview",
    generation_config={"temperature": 0.4}
)

# 厳密な構造化用（統合フェーズ）
model_json = genai.GenerativeModel(
    model_name="gemini-3-flash-preview",
    generation_config={
        "temperature": 0.1, # 丸め込みを防ぐため極力低く設定
        "response_mime_type": "application/json"
    }
)

# ==========================================
# 2. プロジェクト前提条件（共通コンテキスト）
# ==========================================
PROJECT_CONTEXT = """
【プロジェクト前提条件】
- 用途: 工場（特殊建築物）
- 規模: 平屋
- 立地: 法第22条区域
- 工事種別: 新築
- 構造・基礎: S造（Sグレード鉄骨）、杭基礎、構造スラブ
- 特殊要件: 天井クレーン（走行荷重・動荷重考慮）、特殊ガス設備（CO2, LPG, O2）
- 発注方式: 設計施工一括（発注者側にPM/CMあり）
"""

# ==========================================
# 3. プロンプト生成関数（3ステップ）
# ==========================================
def prompt_step1_draft(phase, specialist):
    return f"""
    あなたは日本の建築関連法規と技術体系に精通したシニアアーキテクトです。
    以下の前提条件のもと、【{phase}】における【{specialist}】の設計プロセス、主要な決定事項、必要な法令知識、他分野との調整事項について、専門家の視点から詳細に書き出してください。
    {PROJECT_CONTEXT}
    """

def prompt_step2_review(phase, specialist, draft):
    return f"""
    あなたは非常に厳密に物事を精査するプロフェッショナルです。
    以下のテキストは、【{phase}】における【{specialist}】の設計プロセス案です。
    
    【初期案】
    {draft}
    
    このプロジェクトは「S造平屋、杭基礎、天井クレーンあり、特殊ガス（CO2, LPG, O2）あり、設計施工一括」という非常に難易度の高い条件です。
    上記の初期案に対して、批判的な視点から「**検討すべき内容の抜け漏れ**」や「**考慮すべき条件が見落とされていないか**」を指摘し、追加で検討すべき事項を具体的にリストアップしてください。
    """

def prompt_step3_integrate(phase, specialist, draft, review):
    return f"""
    あなたはプロジェクトを統括するチーフアーキテクトです。
    以下の【初期案】と、【批判的レビュー】を両方読み込み、全ての問題点を解決・網羅した設計プロセスを構築してください。
    
    【初期案】
    {draft}
    
    【批判的レビュー】
    {review}
    
    出力条件：
    情報の抽象化や省略を一切禁止します。特に、意思決定を進める上で「知らない情報があって判断を見誤るのを防ぐためのリサーチ事項」を具体的に出力してください。以下のJSON形式で出力すること。項目数に上限は設けません（指摘事項は全て網羅すること）。
    
    {{
      "phase": "{phase}",
      "specialist": "{specialist}",
      "primary_decisions": [
        {{
          "decision_item": "決定すべき具体的事項",
          "reason_and_context": "なぜそれを決める必要があるのか（特殊条件やレビューでの指摘を交えて具体的に）"
        }}
      ],
      "required_research": [
        {{
          "research_topic": "判断を見誤らないためにリサーチ・確認すべき未知の事項・法令・仕様など",
          "reason_for_research": "なぜこのリサーチが必要なのか（これを知らないとどのような判断ミスが起きるか）"
        }}
      ],
      "critical_coordination": [
        {{
          "target_party": "調整相手（例：構造設計者、ゼネコン施工担当など）",
          "conflict_risk": "発生しうるコンフリクトや手戻りの具体的内容（一般論にせず具体的に）",
          "resolution_strategy": "いつ、どのような情報（図面・計算書・検討書等）を用いて合意形成すべきか"
        }}
      ],
      "inputs": ["この決定を行うために必要な前提情報（箇条書きの文字列リスト）"],
      "outputs": ["この段階での成果物（箇条書きの文字列リスト）"]
    }}
    """

# ==========================================
# 4. Obsidian向け Markdown生成関数（高解像度対応版）
# ==========================================
def create_obsidian_markdown(data, draft_text, review_text):
    phase = data.get("phase", "Unknown_Phase")
    specialist = data.get("specialist", "Unknown_Specialist")
    
    # YAMLフロントマター
    md_content = f"---\n"
    md_content += f"tags: [建築設計プロセス, {phase.replace('・', '')}, {specialist}, 実務ナレッジ]\n"
    md_content += f"phase: {phase}\n"
    md_content += f"specialist: {specialist}\n"
    md_content += f"project_type: S造平屋工場(クレーン・特殊ガス)\n"
    md_content += f"---\n\n"
    md_content += f"# [[{phase}]] における [[{specialist}]] の役割と意思決定\n\n"
    
    # 🎯 主要な決定事項 (オブジェクト配列の処理)
    md_content += "## 🎯 主要な決定事項 (Primary Decisions)\n"
    for item in data.get("primary_decisions", []):
        md_content += f"- **{item.get('decision_item', '')}**\n"
        md_content += f"  - 背景・理由: {item.get('reason_and_context', '')}\n"
    md_content += "\n"

    # 🔍 未知情報の事前リサーチ (オブジェクト配列の処理)
    md_content += "## 🔍 判断ミスを防ぐための事前リサーチ (Required Research)\n"
    for item in data.get("required_research", []):
        md_content += f"- **{item.get('research_topic', '')}**\n"
        md_content += f"  - リサーチが必要な理由(放置するリスク): {item.get('reason_for_research', '')}\n"
    md_content += "\n"

    # ⚠️ 重要調整・リスク事項 (オブジェクト配列の処理)
    md_content += "## ⚠️ 重要調整・リスク事項 (Critical Coordination)\n"
    for item in data.get("critical_coordination", []):
        md_content += f"- **調整対象: [[{item.get('target_party', '関連部署')}]]**\n"
        md_content += f"  - **想定リスク**: {item.get('conflict_risk', '')}\n"
        md_content += f"  - **解決戦略**: {item.get('resolution_strategy', '')}\n"
    md_content += "\n"

    # 📥 前提情報 / 📤 成果物 (単純な文字列リストの処理)
    md_content += "## 📥 前提情報 (Inputs)\n"
    for item in data.get("inputs", []):
        md_content += f"- {item}\n"
    md_content += "\n"

    md_content += "## 📤 成果物 (Outputs)\n"
    for item in data.get("outputs", []):
        md_content += f"- {item}\n"
    md_content += "\n"

    # 🧠 AIの思考プロセス（バックヤード保存）
    md_content += f"---\n## 🧠 AIの思考プロセス（バックヤード）\n"
    md_content += f"### 1. 初期案 (Draft)\n<details><summary>クリックして展開</summary>\n\n{draft_text}\n\n</details>\n\n"
    md_content += f"### 2. PM/CMの批判的レビュー (Review)\n<details><summary>クリックして展開</summary>\n\n{review_text}\n\n</details>\n"
    
    return md_content

# ==========================================
# 5. メインループ
# ==========================================
def main():
    phases = [
        "企画・構想フェーズ", "基本設計フェーズ", "実施設計フェーズ", 
        "確認申請・各種許認可フェーズ", "工事監理・施工図承認フェーズ"
    ]
    specialists = [
        "意匠設計者", "構造設計者", "機械設備設計者", 
        "電気設備設計者", "プラントエンジニア", "ゼネコン施工担当", "PM_CM"
    ]
    
    output_dir = "Architecture_Process_Vault_Ultimate"
    os.makedirs(output_dir, exist_ok=True)
    
    total_combinations = len(phases) * len(specialists)
    current = 1
    
    print(f"🚀 全 {total_combinations} パターン（計 {total_combinations * 3} 回のAPIコール）を開始します...\n")

    for phase in phases:
        for specialist in specialists:
            print(f"[{current}/{total_combinations}] 実行中: {phase} x {specialist}")
            
            try:
                # ステップ1
                draft_res = model_text.generate_content(prompt_step1_draft(phase, specialist))
                draft_text = draft_res.text
                time.sleep(2)
                
                # ステップ2
                review_res = model_text.generate_content(prompt_step2_review(phase, specialist, draft_text))
                review_text = review_res.text
                time.sleep(2)
                
                # ステップ3
                final_res = model_json.generate_content(prompt_step3_integrate(phase, specialist, draft_text, review_text))
                result_data = json.loads(final_res.text)
                
                # Markdown生成
                md_text = create_obsidian_markdown(result_data, draft_text, review_text)
                
                # ファイル保存
                filename = f"{phase.replace('/', '_').replace('・', '')}_{specialist.replace('/', '_').replace('・', '')}.md"
                filepath = os.path.join(output_dir, filename)
                
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(md_text)
                    
                print(f"  └─ ✅ 成功: {filename}")
                    
            except Exception as e:
                print(f"  └─ ❌ エラー発生 ({phase} x {specialist}): {e}")
            
            time.sleep(3) # レートリミット対策
            current += 1

    print(f"\n🎉 完了しました！データは '{output_dir}' フォルダに保存されています。")
    print("生成されたフォルダをObsidianのVaultに配置して、グラフビューを確認してみてください！")

if __name__ == "__main__":
    main()
