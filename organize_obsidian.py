import os
import shutil

# 整理対象のディレクトリ
base_dir = "Architecture_Process_Vault_Ultimate"

# フェーズのプレフィックス定義（並び替え用）
phase_mapping = {
    "企画構想フェーズ": "01_企画構想フェーズ",
    "基本設計フェーズ": "02_基本設計フェーズ",
    "実施設計フェーズ": "03_実施設計フェーズ",
    "確認申請各種許認可フェーズ": "04_確認申請各種許認可フェーズ",
    "工事監理施工図承認フェーズ": "05_工事監理施工図承認フェーズ"
}

def organize_files():
    if not os.path.exists(base_dir):
        print(f"ディレクトリ {base_dir} が見つかりません。")
        return

    # 1. 必要なサブディレクトリを作成
    for prefix in phase_mapping.values():
        dir_path = os.path.join(base_dir, prefix)
        os.makedirs(dir_path, exist_ok=True)
        print(f"ディレクトリ作成/確認: {dir_path}")

    # 2. ファイルをスキャンして移動
    moved_count = 0
    for filename in os.listdir(base_dir):
        if not filename.endswith(".md"):
            continue

        file_path = os.path.join(base_dir, filename)
        
        # すでにディレクトリになっている場合はスキップ
        if os.path.isdir(file_path):
            continue

        # ファイル名からフェーズを判定
        for phase_key, prefix in phase_mapping.items():
            if filename.startswith(phase_key):
                target_dir = os.path.join(base_dir, prefix)
                target_path = os.path.join(target_dir, filename)
                
                # 移動実行
                shutil.move(file_path, target_path)
                print(f"移動: {filename} -> {prefix}/")
                moved_count += 1
                break # 次のファイルへ

    print(f"\n整理完了: 計 {moved_count} ファイルを移動しました。")

if __name__ == "__main__":
    organize_files()
