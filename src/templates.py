"""
SQL filled in by Python for question shapes that never need the model.

Each template must account for every word of the question. Any word it doesn't
recognise returns None, so the question goes to the model instead of being misread.
"""
import re

from src.text_gen import number, ordinal, team_families
from src.text_to_sql import con, words

SEASON = re.compile(r"\b(19[5-9]\d|20[0-2]\d)\b")
DECADE = re.compile(r"\b(19[5-9]|20[0-2])0s\b")
COUNT = re.compile(r"^(how many|(what (is|was) )?the (total )?number of|number of)\b")
# "In 2012, how many..." puts the period first, and every template reads the question from its start
LEADING_PERIOD = re.compile(r"^(in|across|during|over|throughout) (the )?((19[5-9]|20[0-2])\ds?) ")
WINNER = re.compile(r"^(who (won|was the winner|finished first|came first|took (the )?(win|victory))|which (driver|team|constructor) won)\b")
POLE = re.compile(r"^(who|which driver)\b.*\bpole\b")
PLACES = {"second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
PLACE = re.compile(r"^(who|which driver) (finished|came|placed|ended up|crossed the line)( home)?( in)? (?P<place>"
                   + "|".join(PLACES) + r"|\d+(st|nd|rd|th))( place)?\b")
MOST = re.compile(r"^(who|which (driver|team|constructor))\b.*\bmost\b")
CIRCUIT_MOST = re.compile(r"^which (track|circuit|venue)\b.*\bmost\b")
MORE_THAN_ANY = re.compile(r"\bmore\b(.*)\bthan any other( \w+)?$")
PIT_STOPS = re.compile(r"\bpit stops?\b")
AVERAGE_PIT = re.compile(r"^(what (is|was) )?(the )?(average|mean) pit stop\b")
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
COUNT_FILLER = SHARED_FILLER | set("""how many number total career overall all time times grands sprint sprints win wins won victory victories
    pole poles position positions podium podiums finish finishes finished not fail failed retire retired
    retirement retirements dnf dnfs points score scored take took get got claim claimed achieve achieved
    earn earned start started secure secured during altogether rack racked up stood stand""".split())
MOST_FILLER = COUNT_FILLER | set("who which driver team constructor most".split())
CIRCUIT_FILLER = SHARED_FILLER | set("""which track tracks circuit circuits venue venues has have had hosted staged held
    most world championship grands""".split())
PIT_FILLER = SHARED_FILLER | set("how many pit stop stops make made take took during total all there".split())
AVERAGE_FILLER = PIT_FILLER | set("what average mean time duration length".split())
TITLE_FILLER = SHARED_FILLER | set("""who which driver team constructor constructors drivers won was became took
    claimed crowned world champion championship title""".split())


def plain(text: str) -> str:
    return " ".join(words(text))


def has(phrase: str, text: str) -> bool:
    return f" {phrase} " in f" {text} "


def without(phrase: str, text: str) -> str:
    return f" {text} ".replace(f" {phrase} ", " ").strip()


def quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


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


TEAMS = team_families([c for (c,) in con.execute("SELECT DISTINCT constructor FROM f1_results").fetchall()])
# Grouped for ranking. "Lotus" alone is added after this because it spans unrelated teams
TEAM_COLUMN = "CASE " + " ".join(f"WHEN constructor IN ({', '.join(quoted(n) for n in members)}) THEN {quoted(team)}"
                                 for team, members in TEAMS.items() if len(members) > 1) + " ELSE constructor END"
TEAMS["Lotus"] = [name for name in TEAMS if "Lotus" in name and name != "Lotus"] + ["Lotus"]
LOTUS_NOTE = " That covers three separate teams: Team Lotus (1958-1994), the 2010-2011 Lotus team, and Lotus F1 (2012-2015)."
CONSTRUCTORS = {plain(team): team for team in TEAMS}
# McLaren alone means the team, so a surname can't shadow a constructor
DRIVERS = {key: name for key, name in load_drivers().items() if key not in CONSTRUCTORS or " " in key}


def find_name(text: str, names: dict) -> tuple:
    """Full names first, then full names with middle names the data leaves out, then lone surnames."""
    keys = sorted(names, key=len, reverse=True)
    for key in keys:
        if " " in key and has(key, text):
            return names[key], without(key, text)
    for key in keys:  # Juan Manuel Fangio is stored as Juan Fangio
        first, _, last = key.partition(" ")
        match = re.search(rf"(^| ){re.escape(first)}( [a-z]+){{1,2}} {re.escape(last)}( |$)", text) if last else None
        if match:
            return names[key], " ".join((text[:match.start()] + " " + text[match.end():]).split())
    for key in keys:
        if " " not in key and has(key, text):
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


def join_names(names: list) -> str:
    return " and ".join(names)


def race_answer(text: str, season: int) -> dict:
    place = PLACE.search(text)
    if place:
        word = place.group("place")
        place_no = PLACES.get(word) or int(word[:-2])
        text = PLACE.sub("who finished", text)
    round_no, race_name, rest = find_race(text, season)
    if round_no is None or set(rest.split()) - RACE_FILLER:
        return None
    wants_pole = not place and POLE.search(text) is not None and WINNER.search(text) is None
    condition = "grid = 1" if wants_pole else f"position = {place_no if place else 1}"
    sql = f"SELECT driver_name, constructor FROM f1_results WHERE season = {season} AND round = {round_no} AND {condition}"
    rows = con.execute(sql).fetchall()
    if not rows:
        return None
    names = join_names([f"{driver} ({team})" for driver, team in rows])
    if wants_pole:
        answer = f"{names} started on pole at the {season} {race_name}."
    elif place:
        answer = f"{names} finished {ordinal(place_no)} in the {season} {race_name}."
    else:
        answer = f"{names} won the {season} {race_name}."
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
    race, rest = find_name(rest, RACE_NAMES)
    circuit, rest = (None, rest) if race else find_name(rest, CIRCUITS)
    if not (driver or team) or set(rest.split()) - COUNT_FILLER:
        return None

    filters = []
    if driver:
        filters.append(f"driver_name = {quoted(driver)}")
    if team:
        filters.append(team_filter(team))
    if period:
        filters.append(period)
    if race:
        filters.append(f"race_name = {quoted(race)}")
        when = f" at the {race}{when}"
    if circuit:
        filters.append(f"""season * 100 + round IN (SELECT r.season * 100 + r.round FROM f1_races r
                           JOIN f1_circuits c USING (circuit_id) WHERE c.circuit_name = {quoted(circuit)})""")
        when = f" at {circuit}{when}"
    where = " AND ".join(filters)
    sprint = bool(re.search(r"\bsprints?\b", text))
    table = "f1_sprint_results" if sprint else "f1_results"
    if con.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0] == 0:
        return None  # never raced then, so 0 would mislead

    if condition is None and sprint:
        sql = f"SELECT SUM(points) FROM {table} WHERE {where}"
    elif condition is None:
        sql = (None if race or circuit else standings_points_sql(driver, team, period)) or (f"""SELECT (SELECT COALESCE(SUM(points), 0) FROM f1_results WHERE {where})
                                                                    + (SELECT COALESCE(SUM(points), 0) FROM f1_sprint_results WHERE {where})""")
    elif team and not driver and condition in ("position = 1", "grid = 1"):
        # a shared drive puts two of a team's cars on one result
        sql = f"SELECT COUNT(DISTINCT season * 100 + round) FROM {table} WHERE {where} AND {condition}"
    else:
        sql = f"SELECT COUNT(*) FROM {table} WHERE {where} AND {condition}"
    value = con.execute(sql).fetchone()[0]
    if value is None:
        return None
    subject = " for ".join(name for name in (driver, team) if name)
    label = f"{'sprint ' if sprint else ''}{one if value == 1 else many}"
    note = LOTUS_NOTE if team == "Lotus" and not driver and not period else ""
    if sql.startswith("SELECT SUM(points) FROM f1_constructor_standings"):
        entries = con.execute(f"""SELECT constructor, points FROM f1_constructor_standings
                                  WHERE {period} AND {team_filter(team)} AND points > 0 ORDER BY points DESC""").fetchall()
        if len(entries) > 1:  # each chassis and engine pair had its own place in the table
            note = " That adds its entries: " + ", ".join(f"{entry} {number(points)}" for entry, points in entries) + "."
    return {"answer": f"{subject} had {number(value)} {label}{when}.{note}", "sql": sql}


def most_points_sql(by_team: bool, period) -> str:
    """One season comes from the standings, which hold sprint points and old dropped scores. Longer spans add race and sprint points."""
    if period and "BETWEEN" not in period:
        if by_team:
            return f"SELECT {TEAM_COLUMN}, SUM(points) AS n FROM f1_constructor_standings WHERE {period} GROUP BY 1 ORDER BY n DESC LIMIT 2"
        return f"""SELECT d.given_name || ' ' || d.family_name, s.points AS n FROM f1_driver_standings s
                   JOIN f1_drivers d USING (driver_id) WHERE s.{period} ORDER BY n DESC LIMIT 2"""
    column = TEAM_COLUMN if by_team else "driver_name"
    where = f"WHERE {period}" if period else ""
    return f"""SELECT name, SUM(points) AS n FROM (SELECT {column} AS name, points FROM f1_results {where}
               UNION ALL SELECT {column}, points FROM f1_sprint_results {where}) GROUP BY 1 ORDER BY n DESC LIMIT 2"""


def most_answer(text: str) -> dict:
    matched = [m for m in METRICS if re.search(m[0], text)]
    if len(matched) != 1 or re.search(r"\bsprints?\b", text):
        return None  # this only ranks grand prix results
    _, condition, _, many = matched[0]
    period, when, rest = period_filter(text)
    if set(rest.split()) - MOST_FILLER:
        return None
    by_team = re.search(r"\b(team|constructor)\b", text) is not None
    if condition is None:
        sql = most_points_sql(by_team, period)
        rows = con.execute(sql).fetchall()
        if not rows or (len(rows) == 2 and rows[0][1] == rows[1][1]):
            return None
        season = SEASON.search(when)
        so_far = " so far" if season and "BETWEEN" not in period and season_running(int(season.group(1))) else ""
        return {"answer": f"{rows[0][0]} scored the most points{when}{so_far}, with {number(rows[0][1])}.", "sql": sql}
    column = TEAM_COLUMN if by_team else "driver_name"
    total = "COUNT(DISTINCT season * 100 + round)" if by_team and "= 1" in condition else "COUNT(*)"
    where = f"{period} AND {condition}" if period else condition
    sql = f"SELECT {column}, {total} AS n FROM f1_results WHERE {where} GROUP BY 1 ORDER BY n DESC LIMIT 2"
    rows = con.execute(sql).fetchall()
    if not rows or (len(rows) == 2 and rows[0][1] == rows[1][1]):
        return None  # a tie needs a list, not one name
    return {"answer": f"{rows[0][0]} had the most {many}{when}, with {rows[0][1]}.", "sql": sql}


def pit_answer(text: str) -> dict:
    season = SEASON.search(text)
    if season is None:
        return None
    year = int(season.group(1))
    rest = text.replace(season.group(0), "")
    round_no, race_name, rest = find_race(rest, year)
    driver, rest = find_name(rest, DRIVERS)
    if (driver is None and round_no is None) or set(rest.split()) - PIT_FILLER:
        return None  # every stop in a whole season is too broad to be what was meant
    if year < 2011:
        return {"answer": "That isn't in the data: pit stops start in 2011.", "sql": None}
    where = f"season = {year}"
    if driver:
        where += f" AND driver_id IN (SELECT driver_id FROM f1_results WHERE driver_name = {quoted(driver)})"
    if round_no:
        where += f" AND round = {round_no}"
    sql = f"SELECT COUNT(*) FROM f1_pit_stops WHERE {where}"
    value = con.execute(sql).fetchone()[0]
    if value == 0:
        return None
    place = f"the {year} {race_name}" if round_no else str(year)
    stops = f"{value} pit stop{'' if value == 1 else 's'}"
    return {"answer": f"{driver} made {stops} in {place}." if driver else f"There were {stops} in {place}.", "sql": sql}


def average_pit_answer(text: str) -> dict:
    season = SEASON.search(text)
    if season is None:
        return None
    year = int(season.group(1))
    rest = text.replace(season.group(0), "")
    round_no, race_name, rest = find_race(rest, year)
    driver, rest = find_name(rest, DRIVERS)
    if set(rest.split()) - AVERAGE_FILLER:
        return None
    if year < 2011:
        return {"answer": "That isn't in the data: pit stops start in 2011.", "sql": None}
    where = f"season = {year} AND duration <= 120"  # longer means a red flag, not a stop
    if driver:
        where += f" AND driver_id IN (SELECT driver_id FROM f1_results WHERE driver_name = {quoted(driver)})"
    if round_no:
        where += f" AND round = {round_no}"
    sql = f"SELECT AVG(duration) FROM f1_pit_stops WHERE {where}"
    value = con.execute(sql).fetchone()[0]
    if value is None:
        return None
    who = f" for {driver}" if driver else ""
    place = f"the {year} {race_name}" if round_no else str(year)
    return {"answer": f"The average pit stop{who} in {place} took {number(value)} seconds, leaving out red flag stoppages.", "sql": sql}


def team_filter(team: str) -> str:
    return f"constructor IN ({', '.join(quoted(name) for name in TEAMS[team])})"


def standings_points_sql(driver, team, period) -> str:
    """Race rows miss sprint points and old dropped scores, so a single season uses the standings."""
    if period is None or "BETWEEN" in period or (driver and team):
        return None
    if team:
        return f"SELECT SUM(points) FROM f1_constructor_standings WHERE {period} AND {team_filter(team)}"
    return f"""SELECT s.points FROM f1_driver_standings s JOIN f1_drivers d USING (driver_id)
               WHERE s.{period} AND d.given_name || ' ' || d.family_name = {quoted(driver)}"""


def load_circuits() -> dict:
    """Circuit name, id or town for circuits that held a race. George and Villeneuve are drivers first."""
    rows = con.execute("""SELECT DISTINCT c.circuit_id, c.circuit_name, c.locality FROM f1_circuits c
                          JOIN f1_races USING (circuit_id) JOIN f1_results USING (season, round)""").fetchall()
    name_words = {word for name in DRIVERS.values() for word in plain(name).split()}
    found = {}
    for circuit_id, name, town in rows:
        for key in {plain(name), plain(circuit_id), plain(town)}:
            if key and not (" " not in key and key in name_words):
                found.setdefault(key, set()).add(name)
    return {key: names.pop() for key, names in found.items() if len(names) == 1}


CIRCUITS = load_circuits()
RACE_NAMES = {key: name for (name,) in con.execute("SELECT DISTINCT race_name FROM f1_races").fetchall()
              for key in (plain(name), plain(name).replace("grand prix", "gp"))}


def circuit_most_answer(text: str) -> dict:
    period, when, rest = period_filter(text)
    if set(rest.split()) - CIRCUIT_FILLER:
        return None
    where = f"AND r.{period}" if period else ""
    sql = f"""SELECT c.circuit_name, COUNT(*) AS n FROM f1_races r JOIN f1_circuits c USING (circuit_id)
              WHERE (r.season, r.round) IN (SELECT season, round FROM f1_results) {where} GROUP BY 1 ORDER BY n DESC LIMIT 2"""
    rows = con.execute(sql).fetchall()
    if not rows or (len(rows) == 2 and rows[0][1] == rows[1][1]):
        return None
    return {"answer": f"{rows[0][0]} hosted the most Formula 1 races{when}, with {rows[0][1]}.", "sql": sql}


def named_only(names: dict, question: str) -> dict:
    """In free text, a lone surname counts only when capitalised, so "I'd love" isn't John Love. All lower case is taken as typed."""
    if question == question.lower():
        return names
    capitalised = {plain(word) for word in re.findall(r"\w+", question) if word[0].isupper()}
    return {key: name for key, name in names.items() if " " in key or key in capitalised}


def career_lines(text: str, question: str = "") -> list:
    """Each named driver and team, so a comparison gets both overviews. A circuit goes first, so Red Bull Ring isn't Red Bull."""
    circuit, text = find_name(text, CIRCUITS)
    if circuit:
        return [f"{circuit} in "]
    subjects = []
    for names in (named_only(DRIVERS, question), CONSTRUCTORS):
        subject, text = find_name(text, names)
        while subject:
            subjects.append(subject)
            subject, text = find_name(text, names)
    if "Lotus" in subjects:
        at = subjects.index("Lotus")
        subjects[at:at + 1] = ["Team Lotus", "Lotus", "Lotus F1"]
    return [f"{subject} raced in Formula 1 " for subject in subjects]


def focus_lines(question: str) -> list:
    """Corpus sentence starts for a race the question names and a driver in it, or else a career overview."""
    text = plain(question)
    season = SEASON.search(text)
    if season is None:
        return career_lines(text, question)
    year = int(season.group(1))
    round_no, race_name, rest = find_race(text.replace(season.group(0), ""), year)
    driver, _ = find_name(rest, named_only(DRIVERS, question))
    if round_no is None:
        if driver is None:
            return []
        last_round = con.execute("SELECT MAX(round) FROM f1_results WHERE season = ?", [year]).fetchone()[0]
        when = f"After round {last_round} of" if season_running(year) else "At the end of"
        return [f"{when} the {year} season, {driver} "]
    summary = f"The {year} {race_name} "
    return [f"In the {year} {race_name}, {driver} ", summary] if driver else [summary]


def template_answer(question: str) -> dict:
    """An answer with its SQL, or None when the question doesn't fit a template exactly."""
    # "Formula 1" would leave a stray 1, and "more ... than any other" is "most"
    text = MORE_THAN_ANY.sub(r"most\1", plain(question).replace("formula 1", "formula one")).strip()
    lead = LEADING_PERIOD.match(text)
    if lead:
        text = f"{text[lead.end():]} in {lead.group(2) or ''}{lead.group(3)}"
    season = SEASON.search(text)
    if AVERAGE_PIT.search(text):
        return average_pit_answer(text)
    if COUNT.search(text):
        return pit_answer(text) if PIT_STOPS.search(text) else count_answer(text)
    if CIRCUIT_MOST.search(text):
        return circuit_most_answer(text)
    if MOST.search(text):
        return most_answer(text)
    if season is None:
        return None
    year = int(season.group(1))
    rest = text.replace(season.group(0), "")
    if CHAMPION.search(text):
        return title_answer(rest, year)
    if WINNER.search(text) or POLE.search(text) or PLACE.search(text):
        return race_answer(rest, year)
    return None
