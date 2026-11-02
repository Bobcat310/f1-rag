"""Sprint results and pit stops from Jolpica. Run from the repo root: python -m src.extra_data"""
import sys
import time

import duckdb
import pandas as pd

from src.live_data import DB_PATH, backup_database, fetch_pages, race_rows

FIRST_SPRINT_SEASON = 2021
FIRST_PIT_STOP_SEASON = 2011


def duration_seconds(text: str):
    """23.5 for a normal stop, 1:02.3 or longer for a stop that spanned a red flag."""
    try:
        seconds = 0.0
        for part in text.split(":"):
            seconds = seconds * 60 + float(part)
        return seconds
    except (AttributeError, ValueError):
        return None


def sprint_rows(pages: list, season: int) -> list:
    rows = []
    for race in race_rows(pages):
        for r in race["SprintResults"]:
            driver, team = r["Driver"], r["Constructor"]
            rows.append({"season": season, "round": int(race["round"]), "race_name": race["raceName"],
                         "driver_id": driver["driverId"], "driver_name": f"{driver['givenName']} {driver['familyName']}",
                         "constructor": team["name"], "grid": int(r["grid"]), "position": int(r["position"]),
                         "points": float(r["points"]), "laps": int(r["laps"]), "status": r["status"]})
    return rows


def pit_stop_rows(pages: list, season: int) -> list:
    return [{"season": season, "round": int(race["round"]), "race_name": race["raceName"], "driver_id": stop["driverId"],
             "stop": int(stop["stop"]), "lap": int(stop["lap"]), "duration": duration_seconds(stop.get("duration"))}
            for race in race_rows(pages) for stop in race["PitStops"]]


def validate(sprints: pd.DataFrame, stops: pd.DataFrame) -> list:
    """Reasons not to write."""
    problems = []
    if sprints.empty or stops.empty:
        return ["The API returned no sprint or pit stop rows."]
    if sprints.duplicated(["season", "round", "driver_id"]).any():
        problems.append("Duplicate driver in a sprint, so paging may have repeated rows.")
    if sprints.groupby(["season", "round"]).size().min() < 18:
        problems.append("A sprint has fewer than 18 cars, so paging may have lost rows.")
    if stops.duplicated(["season", "round", "driver_id", "stop"]).any():
        problems.append("Duplicate pit stop, so paging may have repeated rows.")
    return problems


def write_tables(sprints: pd.DataFrame, stops: pd.DataFrame, db_path=DB_PATH):
    """Both tables are replaced whole, so running this again is safe."""
    con = duckdb.connect(str(db_path))
    try:
        con.execute("BEGIN")
        con.execute("CREATE OR REPLACE TABLE f1_sprint_results AS SELECT * FROM sprints")
        con.execute("CREATE OR REPLACE TABLE f1_pit_stops AS SELECT * FROM stops")
        con.execute("COMMIT")
        con.execute("CHECKPOINT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    last_season = con.execute("SELECT MAX(season) FROM f1_results").fetchone()[0]
    races = con.execute("SELECT DISTINCT season, round FROM f1_results WHERE season >= ? ORDER BY 1, 2",
                        [FIRST_PIT_STOP_SEASON]).fetchall()
    con.close()

    sprints = []
    for season in range(FIRST_SPRINT_SEASON, last_season + 1):
        sprints += sprint_rows(fetch_pages(season, "sprint"), season)
        print("sprints", season, len(sprints), flush=True)
        time.sleep(0.5)

    stops = []
    for season, round_no in races:
        stops += pit_stop_rows(fetch_pages(season, f"{round_no}/pitstops"), season)
        if round_no == 1:
            print("pit stops reached", season, len(stops), flush=True)
        time.sleep(0.5)

    sprints, stops = pd.DataFrame(sprints), pd.DataFrame(stops)
    problems = validate(sprints, stops)
    if problems:
        sys.exit("Not written: " + "; ".join(problems))
    print("backup", backup_database(), flush=True)
    write_tables(sprints, stops)
    print("written", len(sprints), "sprint rows and", len(stops), "pit stops", flush=True)


if __name__ == "__main__":
    main()
