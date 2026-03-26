# flow - 自動実装フロー (plan → autoplan review → implement → ship)

このコマンドはタスクを受け取り、計画・レビュー・実装・PR作成まで自動で完走します。

## 使い方

```
/flow <タスクの説明>
```

例:
- `/flow embedding モデルを text-embedding-3-large に切り替える`
- `/flow retriever のスコアリングにMMRを追加する`
- 「いつものフローで実行して」と言うとき → このコマンドを使う（タスクを引数に）

---

## 前提: gstack セットアップ

gstack スキルが未インストールの場合は先にセットアップする:

```bash
# gstack が未インストールの場合のみ実行
if [ ! -d ~/.claude/skills/gstack ]; then
  git clone https://github.com/garrytan/gstack.git ~/.claude/skills/gstack && cd ~/.claude/skills/gstack && ./setup
fi
```

---

## フロー手順

### STEP 1: コンテキスト収集

まず現在の状態を把握する:

```bash
git branch --show-current
git status --short
git log --oneline -5
```

タスク内容: **$ARGUMENTS**

### STEP 2: 計画 (Plan)

1. 関連ファイルを特定して読む
2. 変更箇所と影響範囲を分析する
3. 実装アプローチを決定する
4. プランファイルを作成する（`plan.md` または既存のプランファイルに記載）

### STEP 3: autoplan レビュー

gstack の autoplan スキルでプランを自動レビューする:

```bash
cat ~/.claude/skills/gstack/autoplan/SKILL.md
```

autoplan の手順に従い:
- Phase 1: CEO Review（スコープ・戦略）
- Phase 2: Design Review（UI/UXがある場合）
- Phase 3: Eng Review（アーキテクチャ・テスト）
- Phase 4: Final Approval Gate

レビュー結果に基づきプランを修正する。

### STEP 4: 実装 (Implement)

- レビュー済みプランに沿ってコード変更を行う
- 既存のパターン・スタイル・命名規則に従う
- テストがある場合は実行して確認する:
  ```bash
  # テスト実行（存在する場合）
  python -m pytest tests/ -x -q 2>/dev/null || true
  ```

### STEP 5: ship スキルで PR 作成

実装完了後、gstack の ship スキルを読み込んで ship フローを実行する:

```bash
cat ~/.claude/skills/gstack/ship/SKILL.md
```

ship スキルの手順に従い:
- ベースブランチのマージ
- diff レビュー
- コミット・プッシュ
- PR 作成

---

## 注意事項

- 破壊的な変更は実行前にユーザー確認を取る
- 各STEPの完了時にステータスを報告する
