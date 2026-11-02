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
        return f"finished {place} starting from position {grid_int}"
    outcome = NOT_RETIRED.get(row['status'], f"retired ({row['status']})")
    # a car stopping near the end can still be classified and score
    classified = f" but was classified {ordinal(pos_int)}" if row['points'] > 0 else ""
    return f"{outcome}{classified}, grid position {grid_int}"


def result_to_text(row):

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


def standing_to_text(row, after_round=None):
    """after_round marks a season still running, so the sentence doesn't claim it has ended."""
    if pd.isna(row['position']):
        return None

    pos = int(float(row['position']))
    pos_str = "led" if pos == 1 else f"was {ordinal(pos)} in"
    when = (f"After round {after_round} of the {row['season']} season" if after_round
            else f"At the end of the {row['season']} season")

    return (
        f"{when}, {row['driver_name']} {pos_str} the drivers championship "
        f"with {row['points']} points and {plural_wins(row['wins'])}, "
        f"driving for {row['constructor']}."
    )


def constructor_standing_to_text(row, after_round=None):
    if pd.isna(row['position']):
        return None

    pos = int(float(row['position']))
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


def build_corpus(con, live_rounds=None) -> list:
    """All sentences in corpus order. live_rounds maps a running season to its latest round."""
    live_rounds = live_rounds or {}
    results = con.execute("SELECT * FROM f1_results").df()
    sentences = [result_to_text(row) for _, row in results.iterrows()]
    drivers = con.execute("""SELECT s.*, COALESCE(d.given_name || ' ' || d.family_name, s.driver_id) AS driver_name
                             FROM f1_driver_standings s LEFT JOIN f1_drivers d USING (driver_id)""").df()
    for _, row in drivers.iterrows():
        sentences.append(standing_to_text(row, live_rounds.get(row['season'])))
    for _, row in con.execute("SELECT * FROM f1_constructor_standings").df().iterrows():
        sentences.append(constructor_standing_to_text(row, live_rounds.get(row['season'])))
    venues = {(season, round_no): f"{circuit} in {town}" for season, round_no, circuit, town in con.execute(
        "SELECT r.season, r.round, c.circuit_name, c.locality FROM f1_races r JOIN f1_circuits c USING (circuit_id)").fetchall()}
    for (season, round_no, race_name), rows in results.groupby(['season', 'round', 'race_name']):
        if (rows['position'] == 1).any():
            sentences.append(race_summary_to_text(season, race_name, rows, venues.get((season, round_no))))
    return [s for s in sentences if s is not None]
