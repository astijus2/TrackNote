import json
from pathlib import Path
from data_source import fetch_rows
cfg = json.loads(Path('config.json').read_text())
try:
    rows = fetch_rows(cfg)
    print("ROW COUNT:", len(rows))
    print("FIRST 2 ROWS:", rows[:2])
except Exception as e:
    print("ERROR:", type(e).__name__, str(e))
