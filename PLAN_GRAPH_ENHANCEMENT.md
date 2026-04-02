# 課題因果グラフ機能拡張プラン

## 完了済み（2026-04-02）

### iCloud → ローカル移行
- `~/Library/Mobile Documents/.../architectural_rag/` → `~/antigravity_rag/`
- 原因: macOS TCC が iCloud 内の .venv/pyvenv.cfg へのアクセスを拒否（PermissionError）
- launchd plist, launchd_start.sh のパスを新パスに更新済み

### Python 3.9 互換性修正
- `layer_a/memory_ingest.py`: `Optional` import追加, `str | None` → `Optional[str]`
- `layer_a/__init__.py`, `prompts/__init__.py`: 新規作成（空）
- `create_checklist_folders.py`: `/Users/kkk/` → `Path(__file__).parent`

### 課題因果グラフ修正
- `frontend/app/issues/page.tsx:482`: `<Suspense>` に `fallback` prop 追加

---

## 新機能: マインドマップアプリ調査に基づく拡張

### 背景
Miro, Whimsical, XMind, InfraNodus, EasyRCA等の調査に基づく機能提案。
既存スタック: FastAPI + Next.js 14 + ReactFlow v11 + Gemini API + ChromaDB + SQLite

### 提案機能トップ10（優先順位付き）

#### Tier 1: AI活用（既存Gemini APIで実装可能、インパクト大）

1. **AIクラスタリング（自動グルーピング）**
   - 参考: Miro AI
   - 課題ノードをAIが「構造/設備/外装」等に自動分類
   - 実装: Gemini APIでembedding→k-means or HDBSCAN→ReactFlowのGroupNode

2. **AI原因サジェスト**
   - 参考: Whimsical AI
   - ノード選択→Geminiが考えられる原因を自動提案→ブランチ展開
   - 実装: 既存generator.pyのRAGパイプラインを活用

3. **構造的ギャップ検出**
   - 参考: InfraNodus
   - 因果グラフ全体をネットワーク分析し、未接続だが関連すべきクラスターを発見
   - 実装: networkxでグラフ分析→betweenness centrality→gap提案

#### Tier 2: 実務ワークフロー改善（即効性高）

4. **フィッシュボーン/5 Whys統合ビュー**
   - 参考: XMind, EasyRCA
   - 因果グラフから石川ダイアグラムまたは5 Whys分析ビューにワンクリック切替
   - 実装: ReactFlowのカスタムレイアウト

5. **ヒートマップフィルタ**
   - 参考: Obsidian Graph View
   - 重要度・頻度・担当者・工区でノードを色分け
   - 実装: ReactFlowノードのstyle動的変更

6. **折りたたみレイヤー制御**
   - 参考: XMind
   - 深さレベルごとにブランチを折りたたみ/展開
   - 実装: ReactFlowのhidden属性 + レベル計算

7. **ドキュメント/写真リンク**
   - 参考: Obsidian Canvas
   - 各ノードに是正写真・図面PDF・検査報告書を紐付け
   - 実装: 既存artifacts/documents DBテーブルとの結合

#### Tier 3: 長期的価値

8. **リアルタイム共同編集+投票**
   - 参考: MindMeister
   - WebSocket + 投票テーブル追加

9. **AIタイムライン生成**
   - 参考: EasyRCA
   - issues.created_at + d3.js timeline

10. **パターンライブラリ**
    - 参考: XMind
    - ChromaDBに因果パターンembedding保存

### 推奨実装順序
1. Tier 2 の 5（ヒートマップ）と 6（折りたたみ）→ 既存UIの改善、低リスク
2. Tier 1 の 2（AI原因サジェスト）→ Gemini API活用、差別化
3. Tier 2 の 7（ドキュメントリンク）→ 既存RAGとの統合
4. 以降は優先度に応じて

---

## 技術メモ

- プロジェクトパス: `~/antigravity_rag/`
- 起動: `cd ~/antigravity_rag && bash start.sh`
- DB: `~/.antigravity/antigravity.db`
- Backend: FastAPI (port 8000), Basic認証: 環境変数 BASIC_AUTH_PASSWORD 参照
- Frontend: Next.js 14 (port 3000)
- Python: 3.9.6
- 主要ファイル:
  - `routers/issues.py` — 課題因果API（27エンドポイント）
  - `frontend/components/issues/IssueCausalGraph.tsx` — メインReactFlowグラフ
  - `frontend/components/issues/IssueNode.tsx` — ノードコンポーネント
  - `frontend/lib/issue_types.ts` — TypeScript型定義
  - `database.py` — SQLiteスキーマ + migrations

### 次のセッションでの起動手順
```bash
cd ~/antigravity_rag
cat PLAN_GRAPH_ENHANCEMENT.md  # このプランを確認
/autoplan  # gstackフローでレビュー→実装
```
