# flow - 自動実装フロー (plan → implement → PR)

このコマンドはタスクを受け取り、計画・実装・PR作成まで自動で完走します。

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

ship スキルを使うため、gstack が未インストールの場合は先にセットアップする:

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
4. ユーザーに計画を一言で提示し、承認を得る（大きな変更の場合のみ）

### STEP 3: 実装 (Implement)

- 計画に沿ってコード変更を行う
- 既存のパターン・スタイル・命名規則に従う
- テストがある場合は実行して確認する:
  ```bash
  # テスト実行（存在する場合）
  python -m pytest tests/ -x -q 2>/dev/null || true
  ```

### STEP 4: ship スキルで PR 作成

実装完了後、以下のスキルを読み込んで ship フローを実行する:

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

- ブランチは `claude/setup-gstack-03Zcm` で作業する
- PR はこのブランチへのプッシュで作成する
- 破壊的な変更は実行前にユーザー確認を取る
