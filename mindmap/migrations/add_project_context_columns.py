import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "projects.db"

def run_migration():
    if not DB_PATH.exists():
        return
        
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("BEGIN IMMEDIATE")
        
        # projects
        projects_info = {row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()}
        
        if "technical_conditions" not in projects_info:
            conn.execute("ALTER TABLE projects ADD COLUMN technical_conditions TEXT DEFAULT ''")
        if "legal_requirements" not in projects_info:
            conn.execute("ALTER TABLE projects ADD COLUMN legal_requirements TEXT DEFAULT ''")
        if "layer_b_project_id" not in projects_info:
            conn.execute("ALTER TABLE projects ADD COLUMN layer_b_project_id TEXT DEFAULT ''")
        if "gap_check_history" not in projects_info:
            conn.execute("ALTER TABLE projects ADD COLUMN gap_check_history TEXT DEFAULT '[]'")

        # nodes (if exists)
        try:
            nodes_info = {row[1] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()}
            if nodes_info and "source_type" not in nodes_info:
                conn.execute("ALTER TABLE nodes ADD COLUMN source_type TEXT DEFAULT 'manual'")
        except sqlite3.OperationalError:
            pass # Table nodes doesn't exist
            
        conn.commit()
        logger.info("Successfully migrated projects.db for phase 1 context columns.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Database migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
