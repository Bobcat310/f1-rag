"""
SQL filled in by Python for question shapes that never need the model.

Each template must account for every word of the question. Any word it doesn't
recognise returns None, so the question goes to the model instead of being misread.
"""
import re

from src.text_to_sql import con, words

SEASON = re.compile(r"\b(19[5-9]\d|20[0-2]\d)\b")
DECADE = re.compile(r"\b(19[5-9]|20[0-2])0s\b")
COUNT = re.compile(r"^(how many|what (is|was) the (total )?number of)\b")
WINNER = re.compile(r"^(who (won|was the winner|finished first|came first|took (the )?(win|victory))|which (driver|team|constructor) won)\b")
POLE = re.compile(r"^(who|which driver)\b.*\bpole\b")
CHAMPION = re.compile(r"^(who|which (driver|team|constructor)) (won|was|became|took|claimed)\b.*\b(champion|championship|title)\b")

DNF = "status <> 'Finished' AND status <> 'Lapped' AND status NOT LIKE '+%'"
# (pattern on the question, filter, singular label, plural label)
METRICS = [
    (r"\b(not finish|fail(ed)? to finish|retire(d|ments?)?|dnfs?)\b", DNF, "race not finished", "races not finished"),
    (r"\bpoles?\b", "grid = 1", "pole position", "pole positions"),
    (r"\bpodiums?\b", "position <= 3", "podium", "podiums"),
    (r"\bpoints\b", None, "point", "points"),
    (r"\b(wins?|won|victor(y|ies))\b", "position = 1", "win", "wins"),
]

SHARED_FILLER = set("""the a an of in at did does do has have had his her their s for on to from was is were
    race races grand prix gp formula one f1""".split())
RACE_FILLER = SHARED_FILLER | set("""who which what driver team constructor won win winner finished first came took
    victory started start starting pole position qualified claimed got sat""".split())
COUNT_FILLER = SHARED_FILLER | set("""how many number total career overall all time win wins won victory victories
    pole poles position positions podium podiums finish finishes finished not fail failed retire retired
    retirement retirements dnf dnfs points score scored take took get got claim claimed achieve achieved
    earn earned start started secure secured""".split())
TITLE_FILLER = SHARED_FILLER | set("""who which driver team constructor constructors drivers won was became took
    claimed world champion championship title""".split())


def plain(text: str) -> str:
    return " ".join(words(text))


def has(phrase: str, text: str) -> bool:
    return f" {phrase} " in f" {text} "


def without(phrase: str, text: str) -> str:
    return f" {text} ".replace(f" {phrase} ", " ").strip()


def load_drivers() -> dict:
    """Full names, plus a surname when it points to one driver or to the only winner with it."""
    rows = con.execute("SELECT driver_name, MAX(CASE WHEN position = 1 THEN 1 ELSE 0 END) FROM f1_results GROUP BY driver_name").fetchall()
    by_surname = {}
    for name, won in rows:
        by_surname.setdefault(plain(name).split()[-1], []).append((name, won))
    drivers = {plain(name): name for name, _ in rows}
    for surname, people in by_surname.items():
        winners = [name for name, won in people if won]
        if len(people) == 1:
            drivers.setdefault(surname, people[0][0])
        elif len(winners) == 1:
            drivers.setdefault(surname, winners[0])
    return drivers


CONSTRUCTORS = {plain(c): c for (c,) in con.execute("SELECT DISTINCT constructor FROM f1_results").fetchall()}
# McLaren alone means the team, so a surname can't shadow a constructor
DRIVERS = {key: name for key, name in load_drivers().items() if key not in CONSTRUCTORS or " " in key}


def find_name(text: str, names: dict) -> tuple:
    for key in sorted(names, key=len, reverse=True):
        if has(key, text):
            return names[key], without(key, text)
    return None, text


def find_race(text: str, season: int) -> tuple:
    """The race name wins. A circuit or town only counts if it hosted one race that season."""
    rows = con.execute("""SELECT r.round, r.race_name, r.circuit_id, c.locality FROM f1_races r
                          LEFT JOIN f1_circuits c USING (circuit_id) WHERE r.season = ?""", [season]).fetchall()
    for round_no, race_name, _, _ in rows:
        for key in (plain(race_name), plain(race_name).replace("grand prix", "gp")):
            if has(key, text):
                return round_no, race_name, without(key, text)
    found = {(round_no, race_name, key) for round_no, race_name, circuit, town in rows
             for key in (plain(circuit), plain(town or "")) if key and has(key, text)}
    if len({f[0] for f in found}) == 1:
        round_no, race_name, key = sorted(found)[0]
        return round_no, race_name, without(key, text)
    return None, None, text


def season_running(season: int) -> bool:
    raced, planned = con.execute("""SELECT (SELECT MAX(round) FROM f1_results WHERE season = ?),
                                           (SELECT MAX(round) FROM f1_races WHERE season = ?)""", [season, season]).fetchone()
    return raced is not None and raced < planned


def quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def join_names(names: list) -> str:
    return " and ".join(names)


def race_answer(text: str, season: int) -> dict:
    round_no, race_name, rest = find_race(text, season)
    if round_no is None or set(rest.split()) - RACE_FILLER:
        return None
    wants_pole = POLE.search(text) is not None and WINNER.search(text) is None
    condition = "grid = 1" if wants_pole else "position = 1"
    sql = f"SELECT driver_name, constructor FROM f1_results WHERE season = {season} AND round = {round_no} AND {condition}"
    rows = con.execute(sql).fetchall()
    if not rows:
        return None
    names = join_names([f"{driver} ({team})" for driver, team in rows])
    answer = f"{names} started on pole at the {season} {race_name}." if wants_pole else f"{names} won the {season} {race_name}."
    return {"answer": answer, "sql": sql}


def title_answer(text: str, season: int) -> dict:
    if season_running(season) or set(text.split()) - TITLE_FILLER:
        return None
    if re.search(r"\b(constructors?|team)\b", text):
        sql = f"SELECT constructor FROM f1_constructor_standings WHERE season = {season} AND position = 1"
        kind = "constructors"
    else:
        sql = f"""SELECT d.given_name || ' ' || d.family_name FROM f1_driver_standings s
                  JOIN f1_drivers d USING (driver_id) WHERE s.season = {season} AND s.position = 1"""
        kind = "drivers"
    rows = con.execute(sql).fetchall()
    if len(rows) != 1:
        return None
    return {"answer": f"{rows[0][0]} won the {season} {kind} championship.", "sql": sql}


def period_filter(text: str) -> tuple:
    """Returns (SQL condition, phrase for the answer, the text with the period removed)."""
    decade = DECADE.search(text)
    season = SEASON.search(text)
    if decade:
        start = int(decade.group(1)) * 10
        return f"season BETWEEN {start} AND {start + 9}", f" in the {start}s", text.replace(decade.group(0), "")
    if season:
        return f"season = {season.group(1)}", f" in {season.group(1)}", text.replace(season.group(0), "")
    return None, "", text


def count_answer(text: str) -> dict:
    matched = [m for m in METRICS if re.search(m[0], text)]
    if len(matched) != 1:
        return None  # wins from pole is two conditions, and a template only applies one
    _, condition, one, many = matched[0]

    period, when, rest = period_filter(text)
    driver, rest = find_name(rest, DRIVERS)
    team, rest = find_name(rest, CONSTRUCTORS)
    if not (driver or team) or set(rest.split()) - COUNT_FILLER:
        return None

    filters = []
    if driver:
        filters.append(f"driver_name = {quoted(driver)}")
    if team:
        filters.append(f"constructor = {quoted(team)}")
    if period:
        filters.append(period)
    where = " AND ".join(filters)
    if con.execute(f"SELECT COUNT(*) FROM f1_results WHERE {where}").fetchone()[0] == 0:
        return None  # never raced then, so 0 would mislead

    if condition is None:
        sql = standings_points_sql(driver, team, period) or f"SELECT SUM(points) FROM f1_results WHERE {where}"
    elif team and not driver and condition in ("position = 1", "grid = 1"):
        # a shared drive puts two of a team's cars on one result
        sql = f"SELECT COUNT(DISTINCT season * 100 + round) FROM f1_results WHERE {where} AND {condition}"
    else:
        sql = f"SELECT COUNT(*) FROM f1_results WHERE {where} AND {condition}"
    value = con.execute(sql).fetchone()[0]
    if value is None:
        return None
    subject = " for ".join(name for name in (driver, team) if name)
    return {"answer": f"{subject} had {value:g} {one if value == 1 else many}{when}.", "sql": sql}


def standings_points_sql(driver, team, period) -> str:
    """Race rows miss sprint points and old dropped scores, so a single season uses the standings."""
    if period is None or "BETWEEN" in period or (driver and team):
        return None
    if team:
        return f"SELECT points FROM f1_constructor_standings WHERE {period} AND constructor = {quoted(team)}"
    return f"""SELECT s.points FROM f1_driver_standings s JOIN f1_drivers d USING (driver_id)
               WHERE s.{period} AND d.given_name || ' ' || d.family_name = {quoted(driver)}"""


def template_answer(question: str) -> dict:
    """An answer with its SQL, or None when the question doesn't fit a template exactly."""
    text = plain(question)
    season = SEASON.search(text)
    if COUNT.search(text):
        return count_answer(text)
    if season is None:
        return None
    year = int(season.group(1))
    rest = text.replace(season.group(0), "")
    if CHAMPION.search(text):
        return title_answer(rest, year)
    if WINNER.search(text) or POLE.search(text):
        return race_answer(rest, year)
    return None
