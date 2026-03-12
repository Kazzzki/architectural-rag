# ExcelFlow 安全設計書

## 1. 原本保護（大原則）
- ファイルに対するインプレース更新（上書き保存）は禁止。
- 必ず `working` にコピーを作成してから作業。
- 出力は `output` ディレクトリに `xxx__out_<runid>.xlsx` として別名保存。

## 2. Plan-then-Act (自由な編集の禁止)
- MCPツール経由などで、対象ファイルを思いつきで自由編集させない。
- まず `Plan JSON` を作成させ、そのPlanの中に記載された操作しか `Execute` 時には受け付けない。
- エラートラッキングやログ出力はPlan単位、Operation単位で行う設計。

## 3. 停止条件（Safety Checks）
以下の条件が一つでも該当する場合、Dry RunまたはExecutionで処理を停止します。
- `sheet_exists` などの前提条件が満たされていない。
- 推定変更セル数が規定の上限（PoCではデフォルト1000）を超過。
- 列の削除、行の削除、シートの削除（初期PoCでは原則封印アクションとする）。

## 4. 証跡とログ（Auditability）
- `RunLogger` によって全オペレーションごとに成功/失敗のログを保管 (`logs/xxx__run.json`)。
- 実行前と実行後の差分と検証結果も保管 (`logs/xxx__verify.json`)。
- 問題発生時は `run_id` を用いて、Plan、Log、Diff、OutputFileを突合可能。
