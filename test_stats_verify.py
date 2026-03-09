import sys
sys.path.insert(0, '.')
from retriever import get_db_stats
import json

stats = get_db_stats()
print(json.dumps(stats, indent=2, ensure_ascii=False))
