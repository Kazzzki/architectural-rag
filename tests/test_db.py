import sqlite3
conn = sqlite3.connect("data/files.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT original_name, current_path FROM files").fetchall()
for row in rows:
    cp = row["current_path"]
    on = row["original_name"]
    # Check if this matches e-Gov__1771747688_8.pdf
    if "e-Gov" in cp:
        print(f"DB Path: {cp} -> Original: {on}")
