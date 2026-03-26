# 課題因果グラフUI バグ修正プラン（残り7件）

## Background

/investigate で12件のUI問題を発見。5件は修正済み（B1, P1, P3, P4, P9）。残り7件を修正する。

## 修正済み（前回コミット e66d94e）

- **B1**: Delete/Backspaceキーでノード削除 → `onNodesDelete` + `deleteKeyCode` 接続
- **P1**: 「...」ボタンのコンテキストメニュー座標 → ビューポート中央に表示
- **P3**: バッチ削除が逐次 → `Promise.all` 化
- **P4**: MemoPopover 位置固定 → `left:100%` で動的配置
- **P9**: マインドマップレイアウトのカテゴリ間エッジ → 全ノード含むdagre一括計算

## 残り7件の修正

### B2/B3: APIエラー表示不足（HIGH）

**症状**: ノード追加/入力ができない
**根本原因**: `IssueChatPanel.tsx:303` — `res.ok` チェック後に `throw new Error(await res.text())` だが、レスポンスがJSONの場合 `res.text()` が `{"detail":"..."}` のまま表示される

**修正**: `catch` でHTTPステータス別の日本語メッセージを構築
- 500 → 「サーバーエラー: AI処理に失敗しました」
- 422 → 「入力を解析できませんでした」
- その他 → `detail` フィールドを抽出して表示

**ファイル**: `frontend/components/issues/IssueChatPanel.tsx` L297-308

### P2: IssueNode 再レンダリング（MEDIUM）

**症状**: 全ノードが毎回再レンダリングされる（パフォーマンス低下）
**根本原因**: `IssueCausalGraph.tsx:296-312` — `useEffect` 内でインラインの `onClick`, `onContextMenu` 関数を毎回新規作成。`IssueNode` は `React.memo` だが、data内の関数参照が毎回変わるのでmemoが無効

**修正**: `onNodeClick`, `onIssueUpdated` は親から安定した参照で渡されている。問題は `onContextMenu` のインライン関数のみ。`setContextMenu` は `useState` の setter なので安定。ただしクロージャで `iss` をキャプチャするためインライン化は避けられない。
→ **ReactFlowのノードdata比較はshallow equalityなので、関数参照の変更は避けられない。代わりに `IssueNode` の `memo` に custom comparator を追加して issue.id + issue.updated_at のみ比較する**

**ファイル**: `frontend/components/issues/IssueNode.tsx` L126（memo第2引数）

### P5: NoteTimeline 古いデータフラッシュ（LOW）

**症状**: issueId切替時に前のissueのメモが一瞬表示される
**根本原因**: `NoteTimeline.tsx:21` — `useEffect` で `fetchNotes()` を呼ぶが、前のnotesがクリアされない

**修正**: `useEffect` の先頭で `setNotes([])` を追加

**ファイル**: `frontend/components/issues/NoteTimeline.tsx` L21

### P6: EdgeLabelEditor 未接続（HIGH）

**症状**: エッジのラベル・種類を編集するUIが存在するが、どこからも呼び出されない
**根本原因**: `EdgeLabelEditor.tsx` コンポーネントは作成済みだが、`DeletableEdge.tsx` や `IssueCausalGraph.tsx` から import/使用されていない

**修正**: `DeletableEdge.tsx` にエッジダブルクリックで `EdgeLabelEditor` を表示する機能を追加。
エッジホバー時の削除ボタン横に編集ボタン（鉛筆アイコン）も追加。
`EdgeLabelEditor` の表示座標は `EdgeLabelRenderer` の `labelX/labelY` を使用。

**ファイル**:
- `frontend/components/issues/DeletableEdge.tsx` — 編集ボタン + EdgeLabelEditor 表示
- `frontend/components/issues/IssueCausalGraph.tsx` — `onEdgeUpdate` コールバックを `DeletableEdge` の `data` に渡す

### P7: useInteractionMode 未統合（MEDIUM）

**修正**: 現時点では `page.tsx` の `selectedNodeIds` state で十分に機能している。将来的にモード管理が複雑化した場合に統合する。
→ `useInteractionMode.ts` の先頭にTODOコメントを追加

**ファイル**: `frontend/lib/useInteractionMode.ts` L1

### P8: useOptimisticMutation 未統合（MEDIUM）

**修正**: P7と同様。現時点では各コンポーネントが `authFetch` + `onRefresh()` パターンで十分。
→ `useOptimisticMutation.ts` の先頭にTODOコメントを追加

**ファイル**: `frontend/lib/useOptimisticMutation.ts` L1

## 実装順序

```
1. B2/B3: IssueChatPanel エラー表示改善 (5min)
2. P2: IssueNode memo custom comparator (5min)
3. P5: NoteTimeline notes クリア (1min)
4. P6: DeletableEdge + EdgeLabelEditor 接続 (10min)
5. P7/P8: TODOコメント追加 (1min)
6. Commit & push
```
