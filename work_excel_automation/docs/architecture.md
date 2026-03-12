# ExcelFlow アーキテクチャ設計書

汎用Excel処理基盤「ExcelFlow」のアーキテクチャ設計です。
Antigravity非依存の Core/Adapter/Interface 3層構造を採用しています。

## 1. 3層アーキテクチャ

### 1.1 Core Layer (ドメイン・ワークフロー)
- Antigravityや外部の具体的な技術（openpyxl等）に依存しない純粋なビジネスロジック。
- 7フェーズ（intake → discover → match_profile → plan → dry_run → execute → verify）の制御。
- `models.py` にて `Profile`, `Plan`, `RunLog` などの不変なデータ構造を定義。

### 1.2 Adapter Layer (外部インフラ)
- `excel_adapter.py`: openpyxl を用いたExcelの読み書き。
- `file_io.py`: 作業ディレクトリへのファイルコピー、ハッシュ計算、命名規則。
- `logger.py`: JSON形式での実行履歴保存。

### 1.3 Interface Layer (UI / 外部からの呼び出し)
- `cli.py`: コマンドラインからCoreを呼び出すための薄いラッパー。Antigravityがなくても動作する証明。
- `mcp_server.py`: AntigravityなどからLLM Agentが呼び出すためのMCPラッパー。

## 2. 依存関係
- Interface -> Core <- Adapter
- CoreはAdapterの実装詳細（openpyxl等）を知らず、必要なインターフェースを介して委譲する。

## 3. 拡張ポイント
- **Profile追加**: Excelの新しいフォーマット対応はYAMLの追加のみで行う仕組み。
- **Adapter交換**: 将来、openpyxl から Pandas等に変更する場合も、`excel_adapter.py` のインターフェースを満たす新しいクラスを作るだけ。
