"""Pull a season from the free Jolpica API and merge it into DuckDB, the corpus and Chroma."""
import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

import duckdb
import pandas as pd

from src.text_gen import build_corpus

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "f1.db"
CORPUS_PATH = PROJECT_ROOT / "data" / "processed" / "corpus.txt"
BASE_URL = "https://api.jolpi.ca/ergast/f1"
PAGE_SIZE = 100
# Season tables are replaced whole. Lookup tables only gain new rows.
SEASON_TABLES = ["f1_races", "f1_results", "f1_qualifying", "f1_driver_standings", "f1_constructor_standings"]
LOOKUP_TABLES = {"f1_circuits": "circuit_id", "f1_drivers": "driver_id", "f1_constructors": "constructor_id"}


def get_json(url: str, retries: int = 4) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "f1-rag-learning-project"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)["MRData"]
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 5)  # rate limited, so back off


def fetch_pages(season: int, endpoint: str) -> list:
    """Follow the API's offset paging. A race can span two pages, so pages stay separate rows."""
    pages, offset = [], 0
    while True:
        data = get_json(f"{BASE_URL}/{season}/{endpoint}/?limit={PAGE_SIZE}&offset={offset}")
        pages.append(data)
        offset += PAGE_SIZE
        if offset >= int(data["total"]):
            return pages
        time.sleep(0.5)  # stay inside the free rate limit


def fetch_season(season: int) -> dict:
    payload = {}
    for name, endpoint in [("races", "races"), ("results", "results"), ("qualifying", "qualifying"),
                           ("drivers", "driverstandings"), ("constructors", "constructorstandings")]:
        payload[name] = fetch_pages(season, endpoint)
        time.sleep(0.5)
    return payload


def race_rows(pages: list) -> list:
    return [race for page in pages for race in page["RaceTable"]["Races"]]


def standing_rows(pages: list, key: str) -> list:
    return [row for page in pages for table in page["StandingsTable"]["StandingsLists"] for row in table[key]]


def normalize(payload: dict, season: int) -> dict:
    """Map API JSON onto this project's table columns."""
    races, circuits = [], {}
    for race in race_rows(payload["races"]):
        circuit = race["Circuit"]
        races.append({"season": season, "round": int(race["round"]), "race_name": race["raceName"],
                      "circuit_id": circuit["circuitId"], "date": race["date"], "time": race.get("time"), "url": race.get("url")})
        location = circuit["Location"]
        circuits[circuit["circuitId"]] = {"circuit_id": circuit["circuitId"], "circuit_name": circuit["circuitName"],
                                          "locality": location["locality"], "country": location["country"],
                                          "lat": float(location["lat"]), "lng": float(location["long"]), "url": circuit.get("url")}

    results, drivers, constructors = [], {}, {}
    for race in race_rows(payload["results"]):
        for r in race["Results"]:
            driver, team = r["Driver"], r["Constructor"]
            lap = r.get("FastestLap", {})
            results.append({"season": season, "round": int(race["round"]), "race_name": race["raceName"],
                            "driver_id": driver["driverId"], "driver_name": f"{driver['givenName']} {driver['familyName']}",
                            "constructor_id": team["constructorId"], "constructor": team["name"],
                            "grid": int(r["grid"]), "position": int(r["position"]), "points": float(r["points"]),
                            "laps": int(r["laps"]), "status": r["status"], "time": r.get("Time", {}).get("time"),
                            "fastest_lap": lap.get("Time", {}).get("time"), "fastest_lap_rank": lap.get("rank")})
            drivers[driver["driverId"]] = {"driver_id": driver["driverId"], "given_name": driver["givenName"],
                                           "family_name": driver["familyName"], "dob": driver.get("dateOfBirth"),
                                           "nationality": driver.get("nationality"), "number": driver.get("permanentNumber"),
                                           "code": driver.get("code"), "url": driver.get("url")}
            constructors[team["constructorId"]] = {"constructor_id": team["constructorId"], "name": team["name"],
                                                   "nationality": team.get("nationality"), "url": team.get("url")}

    qualifying = [{"season": season, "round": int(race["round"]), "driver_id": q["Driver"]["driverId"],
                   "constructor_id": q["Constructor"]["constructorId"], "position": int(q["position"]),
                   "q1": q.get("Q1"), "q2": q.get("Q2"), "q3": q.get("Q3")}
                  for race in race_rows(payload["qualifying"]) for q in race["QualifyingResults"]]

    driver_standings = [{"season": season, "position": s.get("position"), "points": float(s["points"]), "wins": int(s["wins"]),
                         "driver_id": s["Driver"]["driverId"], "constructor": s["Constructors"][-1]["name"]}
                        for s in standing_rows(payload["drivers"], "DriverStandings")]
    constructor_standings = [{"season": season, "position": s.get("position"), "points": float(s["points"]), "wins": int(s["wins"]),
                              "constructor_id": s["Constructor"]["constructorId"], "constructor": s["Constructor"]["name"]}
                             for s in standing_rows(payload["constructors"], "ConstructorStandings")]

    return {"f1_races": pd.DataFrame(races), "f1_results": pd.DataFrame(results), "f1_qualifying": pd.DataFrame(qualifying),
            "f1_driver_standings": pd.DataFrame(driver_standings), "f1_constructor_standings": pd.DataFrame(constructor_standings),
            "f1_circuits": pd.DataFrame(circuits.values()), "f1_drivers": pd.DataFrame(drivers.values()),
            "f1_constructors": pd.DataFrame(constructors.values())}


def latest_round(tables: dict) -> int:
    return int(tables["f1_results"]["round"].max())


def validate(tables: dict, con, season: int) -> list:
    """Reasons not to write. Rounds already stored must match, or the two sources disagree."""
    problems = []
    results = tables["f1_results"]
    if results.empty or tables["f1_races"].empty:
        return ["The API returned no results or races."]

    rounds = set(results["round"])
    if rounds != set(range(1, max(rounds) + 1)):
        problems.append(f"Rounds are not continuous: {sorted(rounds)}")
    if not rounds <= set(tables["f1_races"]["round"]):
        problems.append("Some results have no matching race.")
    if results.groupby("round").size().min() < 18:
        problems.append("A round has fewer than 18 cars, so paging may have lost rows.")
    if results.duplicated(["round", "driver_id"]).any():
        problems.append("Duplicate driver in a round, so paging may have repeated rows.")

    stored = con.execute("SELECT round, driver_id, position, points FROM f1_results WHERE season = ?", [season]).df()
    merged = stored.merge(results, on=["round", "driver_id"], how="left", suffixes=("_old", "_new"))
    changed = merged[(merged["position_old"] != merged["position_new"]) | (merged["points_old"] != merged["points_new"])]
    if len(changed):
        problems.append(f"{len(changed)} stored result rows differ from the API: {changed[['round', 'driver_id']].head().values.tolist()}")
    return problems


def apply_season(tables: dict, season: int, db_path=DB_PATH) -> dict:
    """Replace the season in one transaction, so a failure leaves the database as it was."""
    con = duckdb.connect(str(db_path))
    added = {}
    try:
        con.execute("BEGIN")
        for table in SEASON_TABLES:
            con.register("incoming", tables[table])
            con.execute(f"DELETE FROM {table} WHERE season = ?", [season])
            con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM incoming")
            con.unregister("incoming")
        for table, key in LOOKUP_TABLES.items():
            con.register("incoming", tables[table])
            before = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM incoming WHERE {key} NOT IN (SELECT {key} FROM {table})")
            added[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] - before
            con.unregister("incoming")
        con.execute("COMMIT")
        con.execute("CHECKPOINT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return added


def backup_database(db_path=DB_PATH) -> Path:
    target = Path(str(db_path) + ".bak")
    shutil.copy2(db_path, target)
    return target


def write_corpus(season: int, last_round: int, finished: bool, db_path=DB_PATH, corpus_path=CORPUS_PATH) -> list:
    con = duckdb.connect(str(db_path), read_only=True)
    sentences = build_corpus(con, None if finished else {season: last_round})
    con.close()
    with open(corpus_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(sentences) + "\n")
    return sentences


def rebuild_index(sentences: list, batch_size: int = 500) -> int:
    """Line numbers are the Chroma ids, so changed lines mean a full rebuild, not a patch."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")
    # delete_collection leaves the old vectors on disk, so every rebuild would add another copy
    shutil.rmtree(PROJECT_ROOT / "chroma_db", ignore_errors=True)
    client = chromadb.PersistentClient(path=str(PROJECT_ROOT / "chroma_db"))
    collection = client.create_collection(name="f1_corpus", metadata={"hnsw:space": "cosine"})
    for i in range(0, len(sentences), batch_size):
        batch = sentences[i:i + batch_size]
        collection.add(documents=batch, embeddings=model.encode(batch).tolist(),
                       ids=[str(j) for j in range(i, i + len(batch))])
    return collection.count()
