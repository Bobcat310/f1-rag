"""Turn database rows into corpus sentences, moved from notebook 02."""
import pandas as pd


def result_to_text(row):
    position = row['position']
    grid = row['grid']

    # Handle DNFs
    try:
        pos_int = int(float(position))
        if pos_int == 1:
            pos_str = "1st (winner)"
        elif pos_int == 2:
            pos_str = "2nd"
        elif pos_int == 3:
            pos_str = "3rd"
        else:
            pos_str = f"{pos_int}th"
    except (TypeError, ValueError):
        pos_str = f"retired ({row['status']})"

    # Handle grid position
    try:
        grid_int = int(float(grid))
        grid_str = f"starting from position {grid_int}"
    except (TypeError, ValueError):
        grid_str = "from an unknown grid position"

    # Fastest lap note
    fastest = ""
    try:
        if int(float(row['fastest_lap_rank'])) == 1:
            fastest = " and set the fastest lap"
    except (TypeError, ValueError):
        pass

    return (
        f"In the {row['season']} {row['race_name']}, "
        f"{row['driver_name']} finished {pos_str} {grid_str}, "
        f"scoring {row['points']} points for {row['constructor']}{fastest}."
    )


def ordinal(pos: int) -> str:
    suffix = 'st' if pos == 1 else 'nd' if pos == 2 else 'rd' if pos == 3 else 'th'
    return f"{pos}{suffix}"


def standing_to_text(row, after_round=None):
    """after_round marks a season still running, so the sentence doesn't claim it has ended."""
    if pd.isna(row['position']):
        return None

    pos = int(float(row['position']))
    pos_str = "led" if pos == 1 else f"was {ordinal(pos)} in"
    when = (f"After round {after_round} of the {row['season']} season" if after_round
            else f"At the end of the {row['season']} season")

    return (
        f"{when}, {row['driver_id']} {pos_str} the drivers championship "
        f"with {row['points']} points and {row['wins']} wins, "
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
            f"with {row['points']} points and {row['wins']} wins."
        )
    return (
        f"In the {row['season']} constructors championship, "
        f"{row['constructor']} finished {ordinal(pos)} "
        f"with {row['points']} points and {row['wins']} wins."
    )


def join_names(names: list) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def race_summary_to_text(season, race_name, rows) -> str:
    """One sentence for a whole race, so a question about it doesn't compete with every car's result."""
    winners = [f"{r['driver_name']} for {r['constructor']}" for _, r in rows[rows['position'] == 1].iterrows()]
    poles = list(rows[rows['grid'] == 1]['driver_name'])
    podium = list(rows[rows['position'] <= 3].sort_values('position')['driver_name'])

    text = f"The {season} {race_name} was won by {join_names(winners)}"
    if poles:
        text += f", with {join_names(poles)} on pole position"
    return f"{text}, and the podium was {join_names(podium)}."


def build_corpus(con, live_rounds=None) -> list:
    """All sentences in corpus order. live_rounds maps a running season to its latest round."""
    live_rounds = live_rounds or {}
    results = con.execute("SELECT * FROM f1_results").df()
    sentences = [result_to_text(row) for _, row in results.iterrows()]
    for _, row in con.execute("SELECT * FROM f1_driver_standings").df().iterrows():
        sentences.append(standing_to_text(row, live_rounds.get(row['season'])))
    for _, row in con.execute("SELECT * FROM f1_constructor_standings").df().iterrows():
        sentences.append(constructor_standing_to_text(row, live_rounds.get(row['season'])))
    for (season, _, race_name), rows in results.groupby(['season', 'round', 'race_name']):
        if (rows['position'] == 1).any():
            sentences.append(race_summary_to_text(season, race_name, rows))
    return [s for s in sentences if s is not None]
