# TODOS — Meeting Transcription Upgrade (Deferred)

## Phase 3 Features (Deferred from autoplan review 2026-04-04)

### M6: ロール別パーソナライズ要約
- Hook: finalize prompt に role パラメータ追加
- 発注者/設計者/施工者の3ビュー
- Effort: ~30min CC

### M7: 話者ダイアライゼーション
- Hook: Gemini speaker diarization GA 待ち
- 参加者名事前登録 → 発言者ラベル付与
- Effort: ~1h CC (Gemini API 次第)

### P9: 類似プロジェクト知見検索
- Hook: project_context_builder.py の cross_project_lessons 活用
- 過去の類似プロジェクト会議決定事項を参考提示
- Effort: ~30min CC

### M9: リアルタイム会議中Q&A
- Hook: M1 の /api/meetings/ask を録音画面から呼べるようにする
- Effort: ~15min CC (UI のみ)

### M10: 日英バイリンガル対応
- Hook: transcription prompt の lang パラメータ化
- コードスイッチング + 翻訳版生成
- Effort: ~1h CC

### M11: 監査証跡・承認フロー
- Hook: meeting_sessions に version + editor 列追加
- 議事録バージョン管理・承認ワークフロー
- Effort: ~2h CC

### M12: 既読トラッキング
- Hook: meeting_read_receipts テーブル
- 関係者の閲覧確認
- Effort: ~1h CC

### P10: プロジェクト文書自動タグ付け
- Hook: scope_resolver を document upload に適用
- PDF/文書アップロード時にプロジェクト自動判定
- Effort: ~30min CC

## Deferred Infrastructure

### P2: プロジェクトタクソノミー
- classification_rules.yaml パターンで十分。本格的な taxonomy は利用状況を見てから
- Effort: ~1h CC

### P3: プロジェクトダッシュボード
- プロジェクト単位で会議・イシュー・文書・タスク横断表示
- Design work needed first
- Effort: ~3h CC

### P7: プロジェクト横断トピックトラッカー
- キーワード監視 → アラート
- Define metrics first
- Effort: ~2h CC

### P8: 会議アナリティクス
- 会議頻度・決定事項数・未解決率・テーマ推移
- Define what to measure first
- Effort: ~2h CC
