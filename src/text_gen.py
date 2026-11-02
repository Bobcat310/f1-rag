"""Turn database rows into corpus sentences, moved from notebook 02."""
import pandas as pd


# Every row has a position, even a retirement, so status decides what happened
NOT_RETIRED = {"Disqualified": "was disqualified", "Excluded": "was excluded", "Withdrew": "withdrew",
               "Did not start": "did not start", "Not classified": "was not classified"}


def ordinal(pos: int) -> str:
    suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(pos % 10, 'th') if pos % 100 not in (11, 12, 13) else 'th'
    return f"{pos}{suffix}"


def finished_race(status: str) -> bool:
    return status in ("Finished", "Lapped") or status.startswith("+")


def outcome_text(row) -> str:
    pos_int = int(float(row['position']))
    grid_int = int(float(row['grid']))
    if finished_race(row['status']):
        place = "1st (winner)" if pos_int == 1 else ordinal(pos_int)
        # grid 0 is a pit lane start or a slot nobody recorded, and the data can't tell which
        start = f"starting from position {grid_int}" if grid_int else "with no grid position recorded"
        return f"finished {place} {start}"
    outcome = "retired" if row['status'] == "Retired" else NOT_RETIRED.get(row['status'], f"retired ({row['status']})")
    # a car stopping near the end can still be classified and score
    classified = f" but was classified {ordinal(pos_int)}" if row['points'] > 0 else ""
    grid = f"grid position {grid_int}" if grid_int else "no grid position recorded"
    return f"{outcome}{classified}, {grid}"


def result_to_text(row):
    if row['status'] == "Fatal accident":
        return f"In the {row['season']} {row['race_name']}, {row['driver_name']} suffered a fatal accident while driving for {row['constructor']}."

    # Fastest lap note
    fastest = ""
    try:
        if int(float(row['fastest_lap_rank'])) == 1:
            fastest = " and set the fastest lap"
    except (TypeError, ValueError):
        pass

    return (
        f"In the {row['season']} {row['race_name']}, "
        f"{row['driver_name']} {outcome_text(row)}, "
        f"scoring {row['points']} points for {row['constructor']}{fastest}."
    )


def plural_wins(count) -> str:
    return "1 win" if count == 1 else f"{count} wins"


def number(value) -> str:
    """Whole where possible, without the rounding :g does past six digits."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def plural(count, one: str, many: str = None) -> str:
    return f"{count} {one if count == 1 else many or one + 's'}"


def standing_to_text(row, after_round=None, season=None):
    """
    after_round marks a season still running, so the sentence doesn't claim it has ended.
    season adds what the race results show: (teams, races, poles, podiums, races not finished).
    """
    if pd.isna(row['position']):
        pos_str = "was not classified in"  # no points, or excluded like Schumacher in 1997
    elif int(float(row['position'])) == 1:
        pos_str = "led" if after_round else "won"
    else:
        pos_str = f"was {ordinal(int(float(row['position'])))} in"
    when = (f"After round {after_round} of the {row['season']} season" if after_round
            else f"At the end of the {row['season']} season")
    teams, record = row['constructor'], ""
    if season:
        team_names, races, poles, podiums, not_finished = season
        teams = join_names(team_names)
        record = (f", from {plural(races, 'race')} with {plural(poles, 'pole position')}, {plural(podiums, 'podium')} "
                  f"and {plural(not_finished, 'race')} not finished")

    return (
        f"{when}, {row['driver_name']} {pos_str} the drivers championship "
        f"with {row['points']} points and {plural_wins(row['wins'])}, "
        f"driving for {teams}{record}."
    )


def constructor_standing_to_text(row, after_round=None):
    if pd.isna(row['position']):
        return (f"In the {row['season']} constructors championship, {row['constructor']} was not classified "
                f"with {row['points']} points and {plural_wins(row['wins'])}.")

    pos = int(float(row['position']))
    if pos == 1 and not after_round:
        return (f"In the {row['season']} constructors championship, {row['constructor']} won the title "
                f"with {row['points']} points and {plural_wins(row['wins'])}.")
    if after_round:
        return (
            f"After round {after_round} of the {row['season']} constructors championship, "
            f"{row['constructor']} was {ordinal(pos)} "
            f"with {row['points']} points and {plural_wins(row['wins'])}."
        )
    return (
        f"In the {row['season']} constructors championship, "
        f"{row['constructor']} finished {ordinal(pos)} "
        f"with {row['points']} points and {plural_wins(row['wins'])}."
    )


def join_names(names: list) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def race_summary_to_text(season, race_name, rows, venue=None) -> str:
    """One sentence for a whole race, so a question about it doesn't compete with every car's result."""
    winners = [f"{r['driver_name']} for {r['constructor']}" for _, r in rows[rows['position'] == 1].iterrows()]
    poles = list(rows[rows['grid'] == 1]['driver_name'])
    podium = list(rows[rows['position'] <= 3].sort_values('position')['driver_name'])

    where = f" at {venue}" if venue else ""
    text = f"The {season} {race_name}{where} was won by {join_names(winners)}"
    if poles:
        text += f", with {join_names(poles)} on pole position"
    return f"{text}, and the podium was {join_names(podium)}."


def team_families(names: list) -> dict:
    """Every constructor name a team raced under. Early entries pair chassis and engine, as in Cooper-Climax."""
    families = {}
    for name in names:
        families.setdefault("Team Lotus" if name.startswith("Lotus-") else name.split("-")[0], []).append(name)
    teams = {name: [name] for name in names}
    teams.update({family: members for family, members in families.items() if len(members) > 1})
    return teams


def top_winners(rows) -> str:
    counts = rows['driver_name'].value_counts()
    best = sorted(counts[counts == counts.max()].index)
    return f"{join_names(best)}, with {plural_wins(int(counts.max()))}{' each' if len(best) > 1 else ''}"


def in_order(values) -> list:
    return list(dict.fromkeys(values))


def titles_text(subject: str, kind: str, seasons: list) -> str:
    if not seasons:
        return ""
    seasons = sorted(seasons)
    return f" {subject} won {plural(len(seasons), f'{kind} championship')} ({join_names([str(s) for s in seasons])})."


def career_to_text(name: str, rows, titles: list, points: float) -> str:
    """rows are the driver's race results in date order, with a team column."""
    first, last = rows['season'].min(), rows['season'].max()
    span = f"from {first} to {last}" if first != last else f"in {first}"
    return (f"{name} raced in Formula 1 {span}, entering {plural(len(rows), 'race')} for {join_names(in_order(rows['team']))}, "
            f"with {plural_wins(int((rows['position'] == 1).sum()))}, {plural(int((rows['grid'] == 1).sum()), 'pole position')}, "
            f"{plural(int((rows['position'] <= 3).sum()), 'podium')} and {number(points)} points."
            f"{titles_text(name, 'drivers', titles)}")


def team_history_to_text(team: str, rows, titles: list, points: float) -> str:
    """Two cars can share one result, so wins and poles count races, not rows."""
    first, last = rows['season'].min(), rows['season'].max()
    span = f"from {first} to {last}" if first != last else f"in {first}"
    races = rows[['season', 'round']].drop_duplicates().shape[0]
    won = rows[rows['position'] == 1]
    wins = won[['season', 'round']].drop_duplicates().shape[0]
    poles = rows[rows['grid'] == 1][['season', 'round']].drop_duplicates().shape[0]
    text = (f"{team} raced in Formula 1 {span}, entering {plural(races, 'race')}, "
            f"with {plural_wins(wins)}, {plural(poles, 'pole position')} and {number(points)} points.")
    text += titles_text(team, "constructors", titles)
    if wins:
        text += f" Its most race wins came from {top_winners(won)}."
    return text


def circuit_to_text(venue: str, rows) -> str:
    """rows are the winners of every race held there."""
    races = rows[['season', 'round']].drop_duplicates().shape[0]
    first, last = rows['season'].min(), rows['season'].max()
    span = f"from {first} to {last}" if first != last else f"in {first}"
    return f"{venue} hosted {plural(races, 'Formula 1 race')} {span}. The most wins there came from {top_winners(rows)}."


def season_records(results) -> dict:
    """(season, driver_id) to the fuller record a standings sentence reports."""
    records = {}
    for key, rows in results.sort_values('round').groupby(['season', 'driver_id']):
        not_finished = int((~rows['status'].map(finished_race)).sum())
        records[key] = (in_order(rows['constructor']), len(rows), int((rows['grid'] == 1).sum()),
                        int((rows['position'] <= 3).sum()), not_finished)
    return records


def summaries(con, results, finished_seasons: set) -> list:
    """One sentence per driver, team and circuit, because a race-by-race corpus has no overview to retrieve."""
    teams = team_families(sorted(results['constructor'].unique()))
    team_of = {name: team for team, members in teams.items() if len(members) > 1 for name in members}
    results = results.assign(team=results['constructor'].map(lambda name: team_of.get(name, name))).sort_values(['season', 'round'])
    sprints = con.execute("SELECT driver_id, constructor, points FROM f1_sprint_results").df()
    sprints['team'] = sprints['constructor'].map(lambda name: team_of.get(name, name))
    driver_sprints = sprints.groupby('driver_id')['points'].sum()
    team_sprints = sprints.groupby('team')['points'].sum()

    driver_titles, team_titles = {}, {}
    for season, driver_id in con.execute("SELECT season, driver_id FROM f1_driver_standings WHERE position = 1").fetchall():
        if season in finished_seasons:
            driver_titles.setdefault(driver_id, []).append(season)
    for season, constructor in con.execute("SELECT season, constructor FROM f1_constructor_standings WHERE position = 1").fetchall():
        if season in finished_seasons:
            team_titles.setdefault(team_of.get(constructor, constructor), []).append(season)

    sentences = []
    for driver_id, rows in results.groupby('driver_id'):
        points = float(rows['points'].sum() + driver_sprints.get(driver_id, 0))
        sentences.append(career_to_text(rows['driver_name'].iloc[0], rows, driver_titles.get(driver_id, []), points))
    for team, rows in results.groupby('team'):
        sentences.append(team_history_to_text(team, rows, team_titles.get(team, []), float(rows['points'].sum() + team_sprints.get(team, 0))))
    circuits = con.execute("""SELECT r.season, r.round, c.circuit_id, c.circuit_name || ' in ' || c.locality || ', ' || c.country AS venue
                              FROM f1_races r JOIN f1_circuits c USING (circuit_id)""").df()
    winners = results[results['position'] == 1].merge(circuits, on=['season', 'round'])
    for _, rows in winners.groupby('circuit_id'):
        sentences.append(circuit_to_text(rows['venue'].iloc[0], rows))
    return sentences


def build_corpus(con, live_rounds=None) -> list:
    """All sentences in corpus order. live_rounds maps a running season to its latest round."""
    live_rounds = live_rounds or {}
    results = con.execute("SELECT * FROM f1_results").df()
    sentences = [result_to_text(row) for _, row in results.iterrows()]
    drivers = con.execute("""SELECT s.*, COALESCE(d.given_name || ' ' || d.family_name, s.driver_id) AS driver_name
                             FROM f1_driver_standings s LEFT JOIN f1_drivers d USING (driver_id)""").df()
    records = season_records(results)
    for _, row in drivers.iterrows():
        sentences.append(standing_to_text(row, live_rounds.get(row['season']), records.get((row['season'], row['driver_id']))))
    for _, row in con.execute("SELECT * FROM f1_constructor_standings").df().iterrows():
        sentences.append(constructor_standing_to_text(row, live_rounds.get(row['season'])))
    venues = {(season, round_no): f"{circuit} in {town}, {country}" for season, round_no, circuit, town, country in con.execute(
        "SELECT r.season, r.round, c.circuit_name, c.locality, c.country FROM f1_races r JOIN f1_circuits c USING (circuit_id)").fetchall()}
    for (season, round_no, race_name), rows in results.groupby(['season', 'round', 'race_name']):
        if (rows['position'] == 1).any():
            sentences.append(race_summary_to_text(season, race_name, rows, venues.get((season, round_no))))
    sentences += summaries(con, results, set(results['season']) - set(live_rounds))
    return [s for s in sentences if s is not None]
