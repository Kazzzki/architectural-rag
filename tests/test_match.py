import sqlite3
from pathlib import Path

path_to_original_name = {}
conn = sqlite3.connect("data/files.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT original_name, current_path FROM files").fetchall()

for row in rows:
    cpath = row["current_path"]
    orig_name = row["original_name"]
    basename = Path(cpath).name
    path_to_original_name[basename] = orig_name

source_pdf = "3_法規チェック/3-1_建築基準法（単体規定）/e-Gov__1771747688_8.pdf"
print("Base name to look for:", Path(source_pdf).name)
print("Is it in the map?", Path(source_pdf).name in path_to_original_name)
if Path(source_pdf).name in path_to_original_name:
    print("Mapped to:", path_to_original_name[Path(source_pdf).name])

