"""One-time fixes to names as they arrived from the source. Safe to run again. Run: python -m src.clean_data"""
import html
from pathlib import Path

import duckdb

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "f1.db"
TEAM_COLUMNS = [("f1_results", "constructor"), ("f1_sprint_results", "constructor"), ("f1_driver_standings", "constructor"),
                ("f1_constructor_standings", "constructor"), ("f1_constructors", "name")]


def unescape_team_names(con) -> int:
    """The source stored Pratt & Whitney with an HTML entity."""
    changed = 0
    for table, column in TEAM_COLUMNS:
        for (name,) in con.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} LIKE '%&%;%'").fetchall():
            con.execute(f"UPDATE {table} SET {column} = ? WHERE {column} = ?", [html.unescape(name), name])
            changed += 1
    return changed


if __name__ == "__main__":
    con = duckdb.connect(str(DB_PATH))
    print("names fixed:", unescape_team_names(con))
    con.close()
