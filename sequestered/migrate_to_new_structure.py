"""
migrate_to_new_structure.py
============================
既存のファイル構成を新構成へ移行するスクリプト。

旧構成:
  建築意匠ナレッジDB/
  ├── 10_参照PDF/01_カタログ/file.pdf
  ├── 20_検索MD/01_カタログ/file.md
  ├── 3_法規チェック/3-1_建築基準法（単体規定）/...
  ├── 4_設計マネジメント/4-1_.../...
  ├── 5_コストマネジメント/5-1_.../...
  ├── uploads/...
  └── 90_処理用データ/chunks/  ← Google Drive 上

新構成:
  建築意匠ナレッジDB/
  ├── 00_未分類/          ← 旧 uploads/
  ├── 01_カタログ/
  │   ├── file.pdf       ← PDF と MD が同じフォルダ
  │   └── file.md
  ├── 02_図面/
  ├── 03_技術基準/
  ├── 04_リサーチ成果物/
  ├── 05_法規/
  │   ├── 建築基準法_単体規定/
  │   ├── 建築基準法_集団規定/
  │   ├── 消防法/
  │   └── その他法令/
  ├── 06_設計マネジメント/
  ├── 07_コストマネジメント/
  └── 99_システム/

実行方法:
  python migrate_to_new_structure.py [--dry-run]

  --dry-run: 実際には移動せず、移動予定ファイルを表示するだけ

注意:
  - 実行前に Google Drive が同期済みであることを確認してください
  - 移行後は POST /api/index?force=true で ChromaDB を再構築してください
"""

import shutil
import argparse
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))
from config import KNOWLEDGE_BASE_DIR, BASE_DIR

# ===== カテゴリマッピング =====
# 旧カテゴリパス → 新カテゴリパス（KNOWLEDGE_BASE_DIR からの相対パス）
CATEGORY_MAP = {
    # 旧 10_参照PDF/ と 20_検索MD/ は自動展開（後述）

    # 法規
    "3_法規チェック/3-1_建築基準法（単体規定）": "05_法規/建築基準法_単体規定",
    "3_法規チェック/3-2_建築基準法（集団規定）": "05_法規/建築基準法_集団規定",
    "3_法規チェック/3-3_消防法":               "05_法規/消防法",
    "3_法規チェック/3-4_その他法令":            "05_法規/その他法令",
    "3_法規チェック":                           "05_法規",  # サブフォルダなし残留物

    # 設計マネジメント
    "4_設計マネジメント/4-1_設計プロセス管理":    "06_設計マネジメント",
    "4_設計マネジメント/4-2_設計品質の第三者検証": "06_設計マネジメント",
    "4_設計マネジメント":                        "06_設計マネジメント",

    # コストマネジメント
    "5_コストマネジメント/5-1_概算コスト": "07_コストマネジメント",
    "5_コストマネジメント":               "07_コストマネジメント",

    # アップロード
    "uploads": "00_未分類",
}

# 旧 10_参照PDF/ と 20_検索MD/ 内のカテゴリマッピング
# パス形式: 10_参照PDF/{old_cat}/ → {new_cat}/
OLD_REFERENCE_PREFIX = "10_参照PDF"
OLD_SEARCH_MD_PREFIX = "20_検索MD"

# 10_参照PDF / 20_検索MD 内のカテゴリ名マッピング
INNER_CATEGORY_MAP = {
    "01_カタログ":        "01_カタログ",
    "02_図面":            "02_図面",
    "03_技術基準":        "03_技術基準",
    "04_リサーチ成果物":   "04_リサーチ成果物",
    "3_法規チェック/3-1_建築基準法（単体規定）": "05_法規/建築基準法_単体規定",
    "3_法規チェック/3-2_建築基準法（集団規定）": "05_法規/建築基準法_集団規定",
    "3_法規チェック/3-3_消防法":               "05_法規/消防法",
    "3_法規チェック/3-4_その他法令":            "05_法規/その他法令",
    "3_法規チェック":                           "05_法規",
    "4_設計マネジメント":                       "06_設計マネジメント",
    "5_コストマネジメント":                     "07_コストマネジメント",
    "uploads":                                  "00_未分類",
}


def resolve_new_category(old_rel: str) -> str:
    """旧相対パスから新カテゴリパスを解決する"""
    old_rel = old_rel.replace("\\", "/")

    # 10_参照PDF/ または 20_検索MD/ プレフィックスを除去してマッピング
    for prefix in (OLD_REFERENCE_PREFIX, OLD_SEARCH_MD_PREFIX):
        if old_rel.startswith(prefix + "/"):
            inner = old_rel[len(prefix) + 1:]
            # inner の先頭部分をカテゴリとして解決
            for old_cat, new_cat in INNER_CATEGORY_MAP.items():
                if inner == old_cat or inner.startswith(old_cat + "/"):
                    suffix = inner[len(old_cat):]  # 残りのサブパス
                    return new_cat + suffix
            # マッピングなし: プレフィックスだけ除去してそのまま
            return inner

    # 直下カテゴリのマッピング
    for old_cat, new_cat in CATEGORY_MAP.items():
        if old_rel == old_cat or old_rel.startswith(old_cat + "/"):
            suffix = old_rel[len(old_cat):]
            return new_cat + suffix

    return old_rel  # マッピングなし: そのまま


def collect_moves(kb_dir: Path) -> list:
    """
    移動すべきファイルのリストを収集する。
    戻り値: [(src_path, dst_path), ...]
    """
    moves = []
    skip_dirs = {"99_システム", ".git", "__pycache__", "chroma_db"}
    # 旧構成の最上位ディレクトリ
    old_top_dirs = {
        "10_参照PDF", "20_検索MD",
        "3_法規チェック", "4_設計マネジメント", "5_コストマネジメント",
        "uploads", "90_処理用データ",
    }

    for src in kb_dir.rglob("*"):
        if src.is_dir():
            continue

        # 除外
        rel = src.relative_to(kb_dir)
        parts = rel.parts
        if any(p in skip_dirs for p in parts):
            continue
        if parts[0].startswith("."):
            continue
        # 90_処理用データ は Google Drive 上の旧チャンクフォルダ → スキップ（ローカルへ移行済み）
        if parts[0] == "90_処理用データ":
            continue

        # 旧構成のトップレベルディレクトリに属するファイルのみ移行対象
        if parts[0] not in old_top_dirs:
            continue

        old_rel_str = str(rel).replace("\\", "/")
        new_cat = resolve_new_category(old_rel_str)
        new_path = kb_dir / new_cat

        if src.resolve() == new_path.resolve():
            continue  # 移動不要

        moves.append((src, new_path))

    return moves


def run_migration(dry_run: bool = False):
    kb_dir = Path(KNOWLEDGE_BASE_DIR)

    if not kb_dir.exists():
        print(f"[ERROR] KNOWLEDGE_BASE_DIR が見つかりません: {kb_dir}")
        sys.exit(1)

    print(f"Google Drive ナレッジベース: {kb_dir}")
    print(f"モード: {'DRY-RUN（実際には移動しません）' if dry_run else '本番実行'}")
    print("=" * 60)

    moves = collect_moves(kb_dir)

    if not moves:
        print("移行対象ファイルはありません。すでに新構成になっているか、旧フォルダが空です。")
        return

    print(f"移行対象: {len(moves)} ファイル\n")

    ok = 0
    skip = 0
    err = 0

    for src, dst in moves:
        rel_src = src.relative_to(kb_dir)
        rel_dst = dst.relative_to(kb_dir)
        print(f"  {rel_src}")
        print(f"  → {rel_dst}")

        if dry_run:
            print()
            continue

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                print(f"  [SKIP] 移動先に同名ファイルが存在します: {rel_dst}")
                skip += 1
            else:
                shutil.move(str(src), str(dst))
                print(f"  [OK]")
                ok += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            err += 1

        print()

    if not dry_run:
        print("=" * 60)
        print(f"完了: {ok} 移動 / {skip} スキップ / {err} エラー")
        print()
        print("次のステップ:")
        print("  1. Google Drive でフォルダ構成を確認してください")
        print("  2. サーバーを再起動してください")
        print("  3. curl -X POST 'http://localhost:8000/api/index?force=true'")
        print("     で ChromaDB を再構築してください")
    else:
        print("=" * 60)
        print(f"DRY-RUN 完了: {len(moves)} ファイルが移行対象です")
        print("実際に移行するには --dry-run なしで実行してください")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ファイル構成を新構成へ移行するスクリプト")
    parser.add_argument("--dry-run", action="store_true", help="実際には移動せず、移動予定を表示するだけ")
    args = parser.parse_args()
    run_migration(dry_run=args.dry_run)
