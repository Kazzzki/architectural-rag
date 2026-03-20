<!-- /autoplan restore point: /root/.gstack/projects/Kazzzki-architectural-rag/claude-enhance-causal-graph-Wj4Eb-autoplan-restore-20260325-140500.md -->

# 課題因果グラフ インタラクティブ機能強化

## Overview

建設PM/CM向け課題因果グラフ（ReactFlow + FastAPI + SQLite + Gemini）に10の新機能を追加し、
ノード操作のインタラクティブ性向上・メモ機能・AI調査機能を実装する。

## Current Architecture

- **Frontend**: React 18 + Next.js 14 + ReactFlow v11 + Tailwind CSS
- **Backend**: FastAPI + SQLite (raw SQL via SQLAlchemy `text()`) + ChromaDB
- **AI**: Gemini 3.1 flash-lite (構造化・分析)
- **Key files**:
  - `frontend/components/issues/IssueCausalGraph.tsx` — ReactFlow graph
  - `frontend/components/issues/IssueNode.tsx` — Custom node component
  - `frontend/components/issues/IssueDetailDrawer.tsx` — Side panel for editing
  - `frontend/components/issues/DeletableEdge.tsx` — Custom edge with delete
  - `frontend/app/issues/page.tsx` — Main page (ProjectGraphView)
  - `frontend/lib/issue_types.ts` — TypeScript types (Issue, IssueEdge, etc.)
  - `routers/issues.py` — All API endpoints (18 endpoints)
  - `database.py` — SQLite schema with idempotent migration system

## Features to Implement (10 features)

### Feature 1: Right-click Context Menu on Nodes

**Problem**: Currently, clicking a node opens the detail drawer. There's no way to perform quick actions without opening the full drawer.

**Solution**: Add `onNodeContextMenu` to ReactFlow. Render a portal-based dropdown with:
- Status change (発生中/対応中/解決済み) — one-click
- Priority change (critical/normal/minor) — one-click
- Start edge creation mode (select source, then click target)
- Duplicate node (POST capture with skip_ai + copy fields)
- Delete node (with confirmation)
- AI investigate (→ Feature 8)
- Add memo (→ Feature 5)

**Files**: New `NodeContextMenu.tsx`, modify `IssueCausalGraph.tsx`, `page.tsx`

**Backend**: No new endpoints needed. Uses existing PATCH/DELETE/POST.

### Feature 2: Double-click Inline Title Editing

**Problem**: Editing a title requires opening the drawer. For quick renames, this is too many clicks.

**Solution**: Double-click on a node title → switches to `<input>` in-place. Enter/blur saves via PATCH.

**Files**: Modify `IssueNode.tsx` only.

**Backend**: No changes — `title` is already in `UPDATABLE_FIELDS`.

### Feature 3: Multi-select & Batch Operations

**Problem**: No way to operate on multiple nodes at once. Large graphs need batch status/assignee changes.

**Solution**:
- Enable ReactFlow `selectionOnDrag` + Shift+click multi-select
- Show floating `BatchActionBar` when 2+ nodes selected
- Batch actions: status change, priority change, assignee set, delete

**Files**: New `BatchActionBar.tsx`, modify `IssueCausalGraph.tsx`, `page.tsx`

**Backend**: New `PATCH /api/issues/batch` endpoint for single-request batch updates.

### Feature 4: Edge Types & Labels

**Problem**: All edges look the same (confirmed=red, unconfirmed=gray). No way to express different causal relationships.

**Solution**:
- Extend `issue_edges` with `label TEXT` and `relation_type TEXT`
- Types: `direct_cause` (solid red), `indirect_cause` (dashed orange), `correlation` (dotted gray), `countermeasure` (solid green)
- Edge label editor popover on edge creation/click
- New PATCH endpoint for edges

**Files**: Modify `DeletableEdge.tsx`, `IssueCausalGraph.tsx`, new `EdgeLabelEditor.tsx`

**Backend**: DB migration (2 columns), update `confirm_edge`, `_edge_row_to_dict`, new `PATCH /api/issues/edges/{edge_id}`.

### Feature 5: Sticky Note Memos on Nodes

**Problem**: `context_memo` exists in the data model but has no visual presence on the graph. Users must open the drawer to see/edit memos.

**Solution**:
- Memo icon (e.g., StickyNote from lucide) on node when `context_memo` is non-empty
- Click icon → popover with textarea for editing
- Badge count/indicator for memo presence

**Files**: Modify `IssueNode.tsx`, new `MemoPopover.tsx`, modify `IssueCausalGraph.tsx`

**Backend**: No changes — uses existing `context_memo` PATCH.

### Feature 6: Timeline Memos (Activity Log)

**Problem**: `context_memo` is a single text field. No history, no timestamps, no attribution.

**Solution**:
- New `issue_notes` table: `id, issue_id, author, content, photo_path, created_at`
- Timeline display in IssueDetailDrawer
- Add note form at bottom of timeline

**Files**: New `NoteTimeline.tsx`, modify `IssueDetailDrawer.tsx`

**Backend**: DB migration (new table + index), 3 new endpoints:
- `GET /api/issues/{issue_id}/notes`
- `POST /api/issues/{issue_id}/notes`
- `DELETE /api/issues/notes/{note_id}`

### Feature 7: Memo Cross-linking

**Problem**: No way to reference other issues or team members within memo text.

**Solution**:
- Parse `#issue-{short_id}` and `@member` syntax in memo/note content
- Render as clickable links (navigate to node, highlight on graph)
- Suggest related memos via ChromaDB similarity search

**Files**: New `memo_linker.ts`, modify `MemoPopover.tsx`, `NoteTimeline.tsx`, `IssueCausalGraph.tsx`

**Backend**: New `GET /api/issues/{issue_id}/related-memos` endpoint.

### Feature 8: Per-node AI Investigation

**Problem**: AI analysis only happens at capture time. No way to deeply analyze a single node's causal chain.

**Solution**:
- "AI Investigate" button in context menu and detail drawer
- 3 modes: RCA (root cause), Impact (downstream), Countermeasure (suggestions)
- Backend traverses causal chain (BFS, max_depth=3) → sends to Gemini

**Files**: New `AIInvestigatePanel.tsx`, modify `IssueDetailDrawer.tsx`

**Backend**: New `POST /api/issues/{issue_id}/ai-investigate` with `{type: "rca"|"impact"|"countermeasure"}`. Shared helper `_traverse_causal_chain()`.

### Feature 9: AI Causal Inference

**Problem**: Users must manually identify causal relationships. Hidden connections go unnoticed.

**Solution**:
- Select 2-3 nodes → "AI因果推定" button in BatchActionBar
- Backend sends selected issues + context to Gemini
- Returns inferred edges as dashed preview on graph
- User approves/rejects each suggested edge

**Files**: New `InferredEdgePreview.tsx`, modify `BatchActionBar.tsx`, `IssueCausalGraph.tsx`

**Backend**: New `POST /api/issues/ai-infer-causation` with `{issue_ids: string[]}`.

### Feature 10: Graph Health Check

**Problem**: No automated way to detect structural issues in the causal graph.

**Solution**:
- Detect: orphan nodes (no edges), causal loops (DFS), unresolved criticals
- AI suggests overlooked causal relationships
- Results displayed in a panel with action buttons

**Files**: New `HealthCheckPanel.tsx`, modify `page.tsx`

**Backend**: New `POST /api/issues/{project_name}/health-check`.

## Database Migrations

1. `ALTER TABLE issue_edges ADD COLUMN label TEXT`
2. `ALTER TABLE issue_edges ADD COLUMN relation_type TEXT DEFAULT 'direct_cause'`
3. `CREATE TABLE issue_notes (id TEXT PK, issue_id TEXT NOT NULL, author TEXT, content TEXT NOT NULL, photo_path TEXT, created_at TEXT NOT NULL)`
4. `CREATE INDEX idx_issue_notes_issue ON issue_notes(issue_id)`

## New API Endpoints (8 total)

| Method | Path | Feature | Purpose |
|--------|------|---------|---------|
| PATCH | `/api/issues/batch` | 3 | Batch update multiple issues |
| PATCH | `/api/issues/edges/{edge_id}` | 4 | Update edge label/type |
| GET | `/api/issues/{issue_id}/notes` | 6 | List timeline notes |
| POST | `/api/issues/{issue_id}/notes` | 6 | Create timeline note |
| DELETE | `/api/issues/notes/{note_id}` | 6 | Delete timeline note |
| GET | `/api/issues/{issue_id}/related-memos` | 7 | ChromaDB similar memos |
| POST | `/api/issues/{issue_id}/ai-investigate` | 8 | AI deep-dive analysis |
| POST | `/api/issues/ai-infer-causation` | 9 | AI causal inference |
| POST | `/api/issues/{project_name}/health-check` | 10 | Graph health check |

## New Frontend Files (9 total)

| File | Feature | Purpose |
|------|---------|---------|
| `NodeContextMenu.tsx` | 1 | Right-click context menu |
| `BatchActionBar.tsx` | 3 | Floating batch action toolbar |
| `EdgeLabelEditor.tsx` | 4 | Edge type/label editor popover |
| `MemoPopover.tsx` | 5 | Sticky note memo popover |
| `NoteTimeline.tsx` | 6 | Timeline activity log component |
| `memo_linker.ts` | 7 | Link syntax parser |
| `AIInvestigatePanel.tsx` | 8 | AI investigation panel |
| `InferredEdgePreview.tsx` | 9 | AI-suggested edge preview |
| `HealthCheckPanel.tsx` | 10 | Health check results panel |

## CEO Review からの追加要件

1. **AI安全策**: AI生成エッジは視覚的に「AI提案」状態を持ち、明示的な承認ワークフロー必須
2. **モバイル対応**: Feature 1（コンテキストメニュー）はロングプレスでも起動
3. **バッチトランザクション**: 一括PATCHはall-or-nothing（部分失敗なし）
4. **ヘルスチェック制限**: AI分析はノード中心性上位50件に限定
5. **Geminiタイムアウト**: 30秒タイムアウト + 「AI一時利用不可」フォールバックUI

## Design Review からの追加要件

### ノード構造図（Node Anatomy）

```
┌─────────────────────────────────────────┐
│ [ステータス円]                  [メモ📝][...]│  ← 右上: アイコンゾーン
│                                          │
│  🔴 タイトルテキスト（ダブルクリック編集） │  ← 中央: メインコンテンツ
│                                          │
│  カテゴリ / ステータス                     │  ← 下段: メタ情報
│ [▼折りたたむ]              [+3 hidden]    │  ← 下端: アクションゾーン
└─────────────────────────────────────────┘
```

- 編集モード中はメモアイコンのクリックを無効化
- マルチセレクト時は青枠ハイライト（他の要素に干渉しない）
- ヘルスチェック警告はノード左端にオレンジ▲バッジ

### インタラクションマップ

| 操作 | 通常モード | マルチセレクトモード | エッジ作成モード | インライン編集モード |
|------|-----------|-------------------|----------------|-------------------|
| シングルクリック | Drawer開く | 選択に追加/解除 | ターゲットノード選択 | 編集確定（blur） |
| ダブルクリック | タイトル編集開始 | タイトル編集開始 | — | — |
| 右クリック | コンテキストメニュー | コンテキストメニュー（一括操作含む） | キャンセル | キャンセル→メニュー |
| ロングプレス(タッチ) | コンテキストメニュー | コンテキストメニュー | — | — |
| Shift+クリック | マルチセレクト開始 | 選択に追加 | — | — |
| ドラッグ | ノード移動 | 選択ノード群を移動 | — | — |
| アイコンクリック(📝) | メモポップオーバー | メモポップオーバー | — | — |
| アイコンクリック(...) | コンテキストメニュー | コンテキストメニュー | — | — |

### パネル優先度スタック

```
レイヤー1（排他）: IssueDetailDrawer ⟷ HealthCheckPanel（同時表示しない）
レイヤー2（共存）: BatchActionBar（選択中のみフローティング表示、上記と共存可）
レイヤー3（共存）: MemoPopover（ノードに紐づくため位置固定、上記と共存可）
レイヤー4（最前面）: NodeContextMenu（一時的、他の操作で自動消去）
```

### 統一非同期パターン（AI機能共通）

1. **ローディング**: ボタンをスピナーに変更 + 「AI分析中...（約10秒）」テキスト
2. **エラー**: 赤背景トースト「AI分析に失敗しました」+ 再試行ボタン
3. **タイムアウト（30秒）**: 自動キャンセル + 「時間がかかっています。後でお試しください」
4. **成功**: 結果をフェードインアニメーションで表示
5. **全AI機能で同一パターンを使用**（AIInvestigatePanel, InferredEdgePreview, HealthCheckPanel）

### 楽観的更新の統一規約

- 全ミューテーション（PATCH/DELETE/POST）は楽観的更新を使用
- サーバーエラー時は自動ロールバック + エラートースト表示
- 削除操作は10秒間のUndo toast付き（ソフトデリート不要、フロントエンドでバッファ）

### 追加API（Design Reviewから）

| Method | Path | Purpose |
|--------|------|---------|
| PATCH | `/api/issues/notes/{note_id}` | タイムラインメモの編集 |

### 追加UIコンポーネント

- **エッジ凡例**: 折りたたみ可能なグラフ内凡例（5種の線種を説明）
- **ノードの「...」ボタン**: コンテキストメニューの可視入口（右クリックが見えない問題対策）
- **メモ入力オートコンプリート**: `#`/`@`入力でタイプアヘッドドロップダウン
- **AI推定エッジ上限**: 1回最大5本、リスト形式でレビュー可能
- **コンテキストメニュー位置補正**: ビューポート境界チェックによるフリップ/シフト

### バッチAPI契約

```typescript
// リクエスト
interface BatchUpdateRequest {
  issue_ids: string[];
  updates: {
    status?: '発生中' | '対応中' | '解決済み';
    priority?: 'critical' | 'normal' | 'minor';
    assignee?: string;
  };
}

// レスポンス（トランザクション: 全成功 or 全失敗）
interface BatchUpdateResponse {
  updated: Issue[];  // 更新後のIssue配列
}
```

## Eng Review からの追加要件

### 実装前の必須修正（Pre-requisites）

1. **`_edge_row_to_dict` / `_issue_row_to_dict`を明示的カラム名SELECTに変更** — 位置インデックス依存は新カラム追加で壊れる
2. **Pydantic `Literal`型でstatus/priority/categoryバリデーション追加** — XSS防止
3. **`list_issues`のエッジクエリにproject_nameフィルタ追加** — 全件スキャン回避
4. **エッジ作成時の重複チェック + self-loop防止追加**
5. **`delete_issue`に`issue_notes`カスケード削除追加**

### アーキテクチャ追加要件

- **インタラクション状態マシン**: `useInteractionMode.ts` — useReducerで型付き状態管理
- **楽観的更新フック**: `useOptimisticMutation.ts` — 全ミューテーションで共用
- **BFS traversal**: `max_nodes=100`キャップ + `max_depth=3`
- **バッチAPI**: `issue_ids`上限100件 + project_name一致検証
- **新ノード配置**: 親ノード相対位置（parent.x + 250, parent.y）
- **Geminiタイムアウト**: `concurrent.futures.ThreadPoolExecutor` + `timeout=30`
- **Short ID**: `#issue-{UUID先頭8文字}` — パーサーで照合
- **MiniMap最適化**: `Map<string, Issue>`でO(1)ルックアップ

### 追加フロントエンドファイル（Eng Reviewから）

| File | Purpose |
|------|---------|
| `useInteractionMode.ts` | インタラクション状態マシン (useReducer) |
| `useOptimisticMutation.ts` | 楽観的更新の集中管理フック |

## Implementation Order (dependency-aware)

```
Phase 0: Pre-requisites（既存コード修正）
  - _row_to_dict を明示的カラムSELECTに変更
  - Pydantic Literal バリデーション追加
  - エッジ重複チェック + self-loop防止
  - list_issues エッジクエリ最適化
  - delete_issue に notes カスケード削除追加

Phase 1: DB migrations + types + shared hooks (foundation)
  - DB migrations (4 statements)
  - TypeScript types 拡張
  - useInteractionMode.ts
  - useOptimisticMutation.ts

Phase 2: Features 1, 2, 5 (independent UI, parallel)
Phase 3: Features 3, 4, 6 (batch ops, edge types, timeline)
Phase 4: Features 8, 9, 10 (AI features, depends on Phase 2-3)
Phase 5: Feature 7 (cross-linking, depends on Features 5+6)
```

## Effort Estimates

| Feature | Human Team | CC+gstack | Compression |
|---------|-----------|-----------|-------------|
| All 10 features + pre-reqs | ~2.5 weeks | ~4-6 hours | ~25x |
| Phase 1 (DB+types) | 2 hours | 5 min | ~24x |
| Phase 2 (UI basics) | 3 days | 30 min | ~48x |
| Phase 3 (batch/edge/timeline) | 3 days | 30 min | ~48x |
| Phase 4 (AI features) | 4 days | 40 min | ~48x |
| Phase 5 (cross-linking) | 1 day | 15 min | ~32x |

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Principle | Rationale | Rejected |
|---|-------|----------|-----------|-----------|----------|
| 1 | CEO | 全10機能を1PRで実装 | P1+P6 | 機能間の結合が強く分割はオーバーヘッド | B)AI先行, C)分割 |
| 2 | CEO | AI生成エッジに承認ワークフロー追加 | P1 | 建設PMで誤った因果推定は実害あり | なし |
| 3 | CEO | Feature 1にロングプレス対応追加 | P1 | 建設現場のタブレット操作で必須 | なし |
| 4 | CEO | ルーター・リファクタリングはスコープ外 | P2 | 動作中のコード改修はocean。追加は既存パターン踏襲 | リファクタ提案 |
| 5 | Design | ノード構造図をプランに追加 | P5 | 10機能が同一ノードに触れる→視覚階層必須 | なし |
| 6 | Design | パネル排他ルール定義 | P5 | Drawer/HealthCheck/BatchBarの同時表示を防ぐ | なし |
| 7 | Design | 統一非同期パターン定義 | P1+P4 | 3つのAI機能で同一UXパターン→DRY | なし |
| 8 | Design | Undo toast追加（ソフトデリート不要） | P3 | フロントバッファで十分、DB変更不要 | ソフトデリート |
| 9 | Design | AI推定エッジ上限5本 | P3 | 20本同時表示はノイズ。5本なら視認性維持 | 制限なし |
| 10 | Design | メモにオートコンプリート追加 | P1 | UUID手打ちは非現実的 | なし |
| 11 | Design | PATCH notes/{id} API追加 | P1 | 編集不可は致命的UX欠陥 | なし |
| 12 | Eng | row_to_dict を明示的カラムに変更 | P5 | 位置インデックスはmigration後に壊れる | なし |
| 13 | Eng | Pydantic Literal型でバリデーション | P1 | XSS防止+データ整合性 | なし |
| 14 | Eng | エッジ重複チェック+self-loop防止 | P1 | AI生成エッジで重複リスク増大 | なし |
| 15 | Eng | useReducer状態マシン | P5 | 4モードの組合せ爆発を型で防ぐ | なし |
| 16 | Eng | useOptimisticMutation フック | P4 | 10機能で同一パターン→集中管理 | 各コンポーネント個別 |
| 17 | Eng | BFS max_nodes=100キャップ | P3 | fan-out爆発でGeminiコンテキスト超過防止 | なし |
| 18 | Eng | Short ID = UUID先頭8文字 | P3 | 新カラム不要、衝突確率は実用上無視可能 | 連番ID, 新カラム |
| 19 | Eng | Gemini timeout = ThreadPoolExecutor | P1 | google.genaiにビルトインtimeoutなし | asyncio |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | clean | 6前提検証、5追加要件。全10機能承認。 |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | clean | 16指摘（3 critical）。ノード構造図・インタラクションマップ追加。 |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | clean | 22指摘（1 critical）。Pre-req 5件、アーキテクチャ追加8件。 |
| Dual Voices | subagent-only | Independent challenge | 3 | complete | CEO/Design/Eng各フェーズで独立レビュー実施。 |

**VERDICT:** APPROVED — 全レビュー完了、19件の自動決定、1件のTASTE DECISION（エッジ4種類）。実装準備完了。
