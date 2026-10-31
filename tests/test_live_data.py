"""Offline checks for the Jolpica mapping and safety checks. Run: python tests/test_live_data.py"""
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.live_data import apply_season, normalize, validate

SEASON = 2099
DRIVER = {"driverId": "newcomer", "givenName": "Ana", "familyName": "Pérez", "dateOfBirth": "2006-01-02",
          "nationality": "Spanish", "permanentNumber": "12", "code": "PER", "url": "u"}
TEAM = {"constructorId": "rookie", "name": "Rookie GP", "nationality": "Spanish", "url": "u"}
CIRCUIT = {"circuitId": "newtrack", "circuitName": "New Track", "url": "u",
           "Location": {"lat": "1.5", "long": "2.5", "locality": "Town", "country": "Spain"}}
RACE = {"round": "1", "raceName": "Test Grand Prix", "date": "2099-03-01", "Circuit": CIRCUIT}


def payload(position="1"):
    finisher = {"position": position, "points": "25", "grid": "2", "laps": "50", "status": "Finished", "Driver": DRIVER,
                "Constructor": TEAM, "Time": {"time": "1:30:00.0"}, "FastestLap": {"rank": "1", "Time": {"time": "1:20.0"}}}
    retired = {**finisher, "status": "Engine", "points": "0"}
    retired.pop("Time")
    retired.pop("FastestLap")
    return {
        "races": [{"RaceTable": {"Races": [RACE]}}],
        "results": [{"RaceTable": {"Races": [{**RACE, "Results": [finisher]}]}},
                    {"RaceTable": {"Races": [{**RACE, "Results": [{**retired, "position": "2", "Driver": {**DRIVER, "driverId": "second"}}]}]}}],
        "qualifying": [{"RaceTable": {"Races": [{**RACE, "QualifyingResults": [{"position": "1", "Driver": DRIVER, "Constructor": TEAM, "Q1": "1:21.0"}]}]}}],
        "drivers": [{"StandingsTable": {"StandingsLists": [{"DriverStandings": [
            {"points": "25", "wins": "1", "Driver": DRIVER, "Constructors": [{"name": "Old Team"}, TEAM]}]}]}}],
        "constructors": [{"StandingsTable": {"StandingsLists": [{"ConstructorStandings": [
            {"position": "1", "points": "25", "wins": "1", "Constructor": TEAM}]}]}}],
    }


tables = normalize(payload(), SEASON)
results = tables["f1_results"]
assert len(results) == 2, "a race split across two API pages must keep both rows"
first = results.iloc[0]
assert first["driver_name"] == "Ana Pérez" and first["position"] == 1 and first["points"] == 25.0
assert pd.isna(results.iloc[1]["time"]) and pd.isna(results.iloc[1]["fastest_lap_rank"])
assert tables["f1_driver_standings"].iloc[0]["constructor"] == "Rookie GP", "latest team of the season is used"
assert pd.isna(tables["f1_driver_standings"].iloc[0]["position"]), "the API can omit position"
assert tables["f1_circuits"].iloc[0]["lng"] == 2.5

small = {name: table.copy() for name, table in tables.items()}
con = duckdb.connect()
con.execute("CREATE TABLE f1_results (season BIGINT, round BIGINT, driver_id VARCHAR, position BIGINT, points DOUBLE)")

problems = validate(tables, con, SEASON)
assert any("fewer than 18" in p for p in problems), problems
many = pd.concat([results.iloc[[0]].assign(driver_id=f"d{i}") for i in range(20)], ignore_index=True)
assert validate({**small, "f1_results": many}, con, SEASON) == []
assert any("Duplicate" in p for p in validate({**small, "f1_results": pd.concat([many, many])}, con, SEASON))
assert any("continuous" in p for p in validate({**small, "f1_results": many.assign(round=5)}, con, SEASON))
assert any("no results" in p.lower() for p in validate({**small, "f1_results": many.iloc[0:0]}, con, SEASON))

con.execute(f"INSERT INTO f1_results VALUES ({SEASON}, 1, 'd0', 9, 25.0)")
assert any("differ" in p for p in validate({**small, "f1_results": many}, con, SEASON)), "a stored result that changed must block the write"

# A failed write must leave nothing behind.
path = Path(__file__).parent / "_rollback_test.db"
path.unlink(missing_ok=True)
disk = duckdb.connect(str(path))
disk.execute("CREATE TABLE f1_races (season BIGINT, round BIGINT, race_name VARCHAR, circuit_id VARCHAR, date DATE, time VARCHAR, url VARCHAR)")
disk.execute(f"INSERT INTO f1_races VALUES ({SEASON}, 9, 'Keep Me', 'x', NULL, NULL, NULL)")
disk.close()
try:
    apply_season(tables, SEASON, path)  # f1_results is missing, so this fails after deleting races
    raise AssertionError("expected the write to fail")
except duckdb.Error:
    pass
disk = duckdb.connect(str(path))
assert disk.execute("SELECT race_name FROM f1_races").fetchall() == [("Keep Me",)], "rollback must restore the deleted rows"
disk.close()
path.unlink()
Path(str(path) + ".wal").unlink(missing_ok=True)

print("live_data checks passed")
