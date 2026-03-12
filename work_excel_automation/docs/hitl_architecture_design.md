# 汎用Excel処理基盤（HITL/詳細解析対応版）設計仕様書

## 1. 提案アーキテクチャ概要
本システムは、未知のExcelフォーマットに対しても安全かつ再利用可能な処理を構築するための汎用基盤です。Antigravityは高度なUI/オーケストレーターとし、処理のコアロジックはCLI/API経由で独立動作する設計とします。

**責務分割（3層アーキテクチャ）**
- **Core (Domain Logic)**: 状態管理、Plan生成・検証、プロファイル結合、差分検証、安全制御（Excel非依存）。
- **Adapter (Infrastructure)**: ファイル読み書き（OpenPyXL等）。Coreの要求を具象化。
- **Interface (Presentation/API)**: コマンド受け付け（CLI）およびMCPラッパー。

**依存関係**
- Interface → Core → Adapter の単方向。CoreはLLMや特定のCLI設定を知りません。

**将来拡張ポイント**
- Adapter層の入れ替えでGoogle SheetsやCSV対応。Trusted Mode（完全自動）への拡張。

**Antigravity依存を避ける設計上の注意点**
- **LLM依存排除**: Core内でAPIリクエストを行わない。確認提示やマッピング推論はInterface/Agentが行い、Coreには確定したJSON（Manifest, Mapping, Contract）のみを渡す。

## 2. 推奨ディレクトリ構成
```text
excelflow_base/
├── inbox/           # (入力) 未処理原本 .xlsx。原則読み取り専用。
├── working/         # (作業) 処理中の一時コピー。
├── output/          # (出力) 処理完了後のファイル。別名保存必須。
├── backup/          # (退避) 原本や中間状態保存用。
├── logs/            # (証跡) 実行ログおよび差分レポート。
├── data/
│   ├── manifests/   # 抽出されたExcel解析結果
│   ├── mappings/    # 列名・意味の対応定義
│   ├── contracts/   # 書き込み・操作の安全ルール
│   ├── profiles/    # 既知フォーマットの抽象定義集
│   └── plans/       # 実行可能な操作命令セット
├── samples/         # テスト用ファイル
├── core/            # (Core層) Plan, Executor等のロジック
├── adapters/        # (Adapter層)
└── interfaces/      # (Interface層) CLI, MCP
```
**命名規則（run_id付き）**: 
`run_1708593402_a1b2c3d4` のようなIDを発行し、ファイル名に付与します（例: `working/monthly_report__run_1708593402...xlsx`）。

## 3. ワークフローモード設計

### A. Onboarding Mode（初回/未知フォーマット）
- **目的**: 初回Excelを詳細解析し、ユーザー確認を経てルール（Mapping/Contract）を固定化する。
- **入力**: 未知のExcelファイル。
- **処理**: 解析(Manifest) → AI推論/質問提示 → ユーザー確認 → Mapping/Contract保存 → Plan → Dry Run → 実行。
- **出力**: Manifest, Mapping Spec, Write Contract, Profile, 出力Excel。
- **停止条件**: 解析エラー、確認拒否、安全性上限エラー。
- **次モードへの遷移**: ルール保存成功で次回からExecution Modeへ。

### B. Execution Mode（既知フォーマット/通常実行）
- **目的**: 確定ルールで自動実行する。
- **入力**: 既知Excelファイル、既存のProfile, Mapping, Contract。
- **処理**: 照合判定 → Plan → Dry Run → 実行。
- **出力**: 自動出力Excel、実行ログ。
- **停止条件**: Profile不一致、Dry Run時のContract違反。
- **次モードへの遷移**: 停止時（フォーマット変更疑い）にRecovery Modeへ。

### C. Recovery Mode（一致崩れ/失敗時）
- **目的**: フォーマットの僅かな崩れを世知し、最小限の再確認で復旧する。
- **入力**: 処理失敗Excel、旧ルールのProfile等。
- **処理**: Manifest差分比較 → 崩れた箇所の提示・確認 → Mapping/Contract更新 → 再実行。
- **出力**: 更新されたルール、出力Excel。
- **停止条件**: 差分大（同一フォーマットとみなせない場合）。

## 4. 汎用ワークフロー設計（詳細）

1. **Intake**: 原本を `inbox` に配置しハッシュ計算、`working` へコピー。
2. **Workbook Profiling**: `working` を読み込み、構造・結合セル・ヘッダ候補を抽出し `Manifest` 出力。
3. **User Confirmation**: AIが `Manifest` から推論しユーザーへ確認。承認結果を得る。
4. **Profile Matching**: 承認結果から `Mapping Spec` と `Write Contract` を作成/照合。
5. **Plan**: `Plan JSON` の組み立て。
6. **Dry Run**: `Plan`を `Write Contract` と照らし合わせ、影響（変更セル数等）と違反の有無を検証。
7. **Execute**: 検証済み `Plan` を実行。
8. **Verify**: 想定外の変更がないかをチェック。成功なら `output` へ保存。
9. **Persist Learning**: ルールを正式登録し次回以降に備える。

## 5. Workbook Manifest仕様（v1）

```json
{
  "manifest_version": "1.0",
  "run_id": "run_170850_abcd",
  "file_info": { "filename": "data.xlsx", "extension": ".xlsx", "size_bytes": 140500, "hash": "sha256:..." },
  "workbook_meta": { "sheet_count": 1, "protected": false },
  "sheets": [
    {
      "sheet_name": "売上データ",
      "dimensions": "A1:F500",
      "used_range": { "start": [1,1], "end": [500,6] },
      "hidden_rows": [], "hidden_cols": ["C"], "merged_cells": ["A1:F1"],
      "header_candidates": [ {"row": 2, "values": ["日付", "店舗名", "客数", "売上", "原価", "利益"]} ],
      "table_candidates": [ {"start_row": 3, "end_row": 500} ],
      "formula_regions": ["F3:F500"],
      "column_profiles": [ {"col_idx": 4, "col_label": "売上", "inferred_type": "currency", "null_ratio": 0.0, "unique_est": 450} ],
      "risk_flags": ["has_hidden_columns", "title_merge_detected"],
      "profiling_confidence": 0.95
    }
  ]
}
```

## 6. User Confirmation設計（HITL）

**AIの「確認候補提示」フォーマット**
```json
{
  "guesses": { "target_sheet": "売上データ", "header_row": 2, "intent": "売上集計", "proposed_write_area": "G列以降への計算追記" },
  "questions": [ "Q1: 対象表は2行目をヘッダとします。よろしいですか？", "Q2: G列に利益率を追加します。よろしいですか？", "Q3: 既存データ（A~F列）は保護（上書き禁止）で進めますか？" ]
}
```
ユーザーの承認結果はJSON形式で保存され、後続のマッピング・契約生成に渡されます。

## 7. Mapping Spec仕様（v1）

```json
{
  "mapping_version": "1.0",
  "profile_id": "monthly_sales_v1",
  "sheet_name": "売上データ",
  "header_row": 2,
  "field_mappings": [
    { "source_header": "店舗名", "canonical_field": "store_name", "confidence": 1.0, "confirmed_by_user": true },
    { "source_header": "売上", "canonical_field": "revenue_amount", "confidence": 0.9, "confirmed_by_user": true }
  ],
  "unmapped_headers": ["客数", "利益"]
}
```

## 8. Write Contract仕様（v1）

```json
{
  "contract_version": "1.0",
  "profile_id": "monthly_sales_v1",
  "target_sheet": "売上データ",
  "read_only_ranges": ["A1:F1048576"], 
  "write_allowed_ranges": ["G2:H1048576"],
  "formula_managed_ranges": ["G3:G1048576"],
  "protected_columns": ["日付", "店舗名", "売上", "原価"],
  "row_boundary_rule": "stop_at_first_empty_in_col_A",
  "forbidden_operations": ["delete_row", "delete_column", "delete_sheet", "overwrite_cell"],
  "postconditions": [ "no_changes_in_read_only_ranges", "sheet_count_unchanged" ]
}
```
**ルール**: `Dry Run`/`Verify` 時に、操作範囲が `read_only_ranges` に被る、または `forbidden_operations` が含まれれば即時停止。

## 9. Profile YAML仕様（v1）

```yaml
profile_version: "1.0"
profile_id: "generic_tabular_v1"
sheet_candidates: [".*データ.*", "Sheet1"]
header_aliases:
  "案件名": ["工事名", "プロジェクト名", "対象案件"]
  "金額": ["工事費", "売上", "単価", "費用"]
  "日付": ["着工日", "完了日", "計上月"]
required_fields:
  - name: "案件名"
    logical_type: "string"
  - name: "金額"
    logical_type: "numeric"
optional_fields: []
transforms: []
validations:
  min_data_rows: 1
profile_match_rules:
  min_match_ratio: 0.8
```

## 10. Plan JSON仕様（v1）

```json
{
  "version": "1.0",
  "run_id": "run_170850_abcd",
  "input_file": "working/file.xlsx",
  "output_file": "output/file_out.xlsx",
  "matched_profile": "generic_tabular_v1",
  "manifest_ref": "data/manifests/run_170850_abcd.json",
  "mapping_ref": "data/mappings/sales_v1.json",
  "write_contract_ref": "data/contracts/sales_v1.json",
  "preconditions": [ {"type": "sheet_exists", "sheet": "売上データ"} ],
  "operations": [
    { "op": "insert_column", "sheet": "売上データ", "params": {"idx": 7, "header_name": "利益率"}, "reason": "利益率列の追加" },
    { "op": "set_formula", "sheet": "売上データ", "params": {"row": 3, "col": 7, "formula": "=F3/D3"}, "reason": "数式設定" },
    { "op": "fill_down", "sheet": "売上データ", "params": {"col": 7, "start_row": 3, "end_row": 500, "formula": "=F{row}/D{row}"}, "reason": "数式コピー" }
  ],
  "validations": [ {"type": "contract_enforcement", "params": {}} ],
  "approval_required": true
}
```

## 11. CLI仕様（Antigravity非依存）

- `discover --input inbox/file.xlsx --out_manifest data/manifests/xxx.json`
- `confirm --manifest data/manifests/xxx.json --mapping spec.json --contract contract.json`
- `plan --input inbox/file.xlsx --profile my_profile --out_plan plans/xxx.json`
- `run --plan plans/xxx.json --mode safe` (終了コード: 0=成功, 1=エラー, 2=契約違反/DryRun失敗, 3=前提不一致)
- `verify --original inbox/file.xlsx --output output/file_out.xlsx`

## 12. MCPラッパー仕様（Antigravity用）

**高レベルツール**:
- `profile_workbook`: ファイルをパースしManifestを生成。
- `propose_confirmation_items`: Manifestから確認事項(質問と推奨案)を生成。
- `save_confirmed_mapping` / `save_write_contract`: ユーザー承認の保存。
- `build_plan`: Manifestや要請からPlan生成。
- `dry_run_plan`: PlanとContractを比較し安全チェック。
- `execute_plan`: 安全なPlanを実行。
- `verify_run`: 実行後の整合性チェック。

## 13. 安全設計
- **原本保護**: CLI/Coreは原本(inbox)の変更をロック。
- **契約チェック**: Contractに定義された `forbidden_operations` 等がPlanにあればDry Runで停止。
- **後条件検証**: 実行後に予定外のシートや保護領域が変更されていないか差分チェック。
- **Safe Mode**: 原則Safe Mode動作。完全自動化(Trusted)は将来拡張とする。

## 14. PoC実装ステップ

### Phase 1: Onboarding Mode最小版
- **やること**: Manifest抽出、確認事項の一時保存、Mapping/Contractの初期実装、これに基づくPlan生成、Dry Run(保護域検証)、実行。
- **完了条件**: 初見Excelを取り込み、AIと人間で合意を取り、許可範囲内でのみ列追加/数式展開が安全にできること。
- **まだやらない**: 2回目以降の自動照合（Execution）、フォーマット変更時の復旧（Recovery）。

### Phase 2: Profile matching強化 + Recovery Mode
- **やること**: 既知フォーマットとの照合判定、差分抽出。
- **完了条件**: 前月と一部列構成が変わったファイルを入れた際、ズレた箇所だけ確認提示し実行できること。

### Phase 3: Trusted Mode条件設計
- **やること**: 自動化度を高め、API等からの連続実行を可能にするための条件設計。

## 15. Antigravity運用手順（実務想定）

**A. 初回（未知フォーマット）**
1. ユーザー指示 → 2. `profile_workbook`(Manifest生成) → 3. `propose_confirmation_items`(確認生成) → 4. ユーザーに質問(HITL) → 5. 承認後 `save_*` でルール固定 → 6. `build_plan` → 7. `dry_run_plan`(安全確認) → 8. `execute_plan` → 9. `verify_run` とリンク提示。

**B. 2回目以降（既知フォーマット）**
1. 目的ファイル投入 → 2. Profile照合と一致率確認 → 3. `build_plan` → 4. `dry_run_plan` → 5. `execute_plan` → 6. `verify_run`。

**C. 崩れた時（Recovery）**
1. 照合失敗 → 2. 前Manifestとの差分抽出 → 3. ズレの再確認提示(HITL) → 4. ルール再固定 → 5. 再実行。

## 16. Antigravityで使う確認質問テンプレ

```text
分析の結果、本ファイルの処理方針について、以下のルールで固定化してよろしいでしょうか？

1. 【対象範囲】：「[対象シート名]」シートの [X] 行目をヘッダと認識します。
2. 【列の意味】：「[列A]」は売上金額、「[列B]」は案件名として扱います。
3. 【書き込みルール】：既存データ（A〜F列）は上書き・削除せず保護し、追記は [G列以降] のみとします。
4. 【追加処理】：[G列] に数式（利益率）を最終行までコピーします。
5. 【異常時】：想定外のフォーマット変更を検知した場合は、安全のため実行を即時停止します。

問題なければ「このまま進めて」とお知らせください。修正点があればご指示ください。
```

## 17. リスク・不確実点・確認事項
- **技術的制約**: ローカル.xlsx仕様による非表示行列の確実な取得の難易度。複雑な動的配列数式の評価不可。
- **失敗パターン**: ヘッダがなくデータ行のみの場合のマッピング。
- **設計トレードオフ**: 安全性（Write Contract）を過度に厳しくすると、実務ファイルの軽微な揺らぎ（毎月1列追加される等）で停止エラーが頻発する。
- **初期PoCで割り切る**: 列・行削除フェーズは省略。複雑なシート間参照の静的解析は非対応。
- **後続確認**: 数式の計算結果の最終的妥当性は利用者が確認。
