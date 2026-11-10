"""Text-to-SQL path, moved from notebook 05. See that notebook for how it was evaluated."""
import os
import re
import unicodedata
from pathlib import Path

import duckdb
import ollama

PROJECT_ROOT = Path(__file__).resolve().parent.parent

con = duckdb.connect(str(PROJECT_ROOT / "data" / "f1.db"), read_only=True)
client = ollama.Client(host=os.environ.get("F1_OLLAMA_URL", "http://localhost:11434"))

MODEL = "llama3.2:3b"
# temperature 0 and a fixed seed keep runs close, though not always identical
LLM_OPTIONS = {"temperature": 0, "seed": 42}


BASE_PROMPT = """Write one DuckDB SELECT statement. Return only the SQL.

f1_results (one row per driver per race): season, round, race_name, driver_id, driver_name, constructor, grid, position, points
position = 1 is a win. Match race_name exactly with = and the full name from the question.
Only filter on names and years that appear in the question."""

# (when the question matches, the note to add, an example of the pattern)
HINTS = [
    (r"\braces (were|have been) (held|run)\b", "To count races, use f1_races: season, round, race_name, circuit_id, date. Do not join it.",
     "Q: How many races were held in 1999?\nA: SELECT COUNT(*) FROM f1_races WHERE season = 1999"),
    (r"\bpodiums?\b", "A podium means position <= 3.",
     "Q: How many podiums did Graham Hill score?\nA: SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Graham Hill' AND position <= 3"),
    (r"\bpoles?\b", "A pole position means grid = 1.",
     "Q: How many pole positions did Jim Clark take?\nA: SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Jim Clark' AND grid = 1"),
    (r"\b(not finish|fail(ed)? to finish|retire|dnf)", "Not finishing means status <> 'Finished' AND status <> 'Lapped' AND status NOT LIKE '+%'.",
     "Q: How many races did Jean Alesi fail to finish in 1995?\nA: SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Jean Alesi' AND season = 1995 AND status <> 'Finished' AND status <> 'Lapped' AND status NOT LIKE '+%'"),
    (r"\bper season\b", "An average per season is SUM(points) / COUNT(DISTINCT season).",
     "Q: What is the average points scored by Williams per season?\nA: SELECT SUM(points) / COUNT(DISTINCT season) AS average FROM f1_results WHERE constructor = 'Williams'"),
    (r"\bpoints\b(?!.*per season)",
     "Total points means SUM(points), not COUNT(*). One season's points for a driver are in f1_driver_standings, which counts sprints too.",
     "Q: Which driver scored the most points in 1996?\nA: SELECT d.given_name || ' ' || d.family_name, s.points FROM f1_driver_standings s JOIN f1_drivers d USING (driver_id) WHERE s.season = 1996 ORDER BY s.points DESC LIMIT 1"),
    (r"\bconstructors?'? championships?\b", "Use f1_constructor_standings: season, position, points, wins, constructor.",
     "Q: Which team won the 2011 constructors championship?\nA: SELECT constructor FROM f1_constructor_standings WHERE season = 2011 AND position = 1"),
    (r"\bdrivers?'? championships?\b", "Use f1_driver_standings: season, position, points, wins, driver_id.",
     "Q: Who won the 2011 drivers championship?\nA: SELECT driver_id FROM f1_driver_standings WHERE season = 2011 AND position = 1"),
    (r"\bpit stops?\b", "Use f1_pit_stops: season, round, race_name, driver_id, stop, lap, duration (in seconds). It starts in 2011.",
     "Q: How many pit stops did Kimi Raikkonen make in 2013?\nA: SELECT COUNT(*) FROM f1_pit_stops WHERE driver_id = 'raikkonen' AND season = 2013"),
    (r"\b(average|mean|fastest|slowest|quickest)\b.*\bpit stops?\b|\bpit stops?\b.*\b(average|mean|fastest|slowest|quickest)\b",
     "A stop over 120 seconds is a red flag stoppage, so filter with duration <= 120. Durations can be NULL.",
     "Q: What was the average pit stop time in 2019?\nA: SELECT AVG(duration) FROM f1_pit_stops WHERE season = 2019 AND duration <= 120"),
    (r"\b(lotus|cooper|brabham|mclaren|brm|march|matra|shadow|eagle)\b",
     "Older teams appear under several constructor names, such as Brabham-Repco. Match with constructor LIKE '%Name%'.",
     "Q: How many podiums did Cooper have in 1962?\nA: SELECT COUNT(*) FROM f1_results WHERE constructor LIKE '%Cooper%' AND season = 1962 AND position <= 3"),
    (r"\b(american|argentine|australian|austrian|belgian|brazilian|british|canadian|dutch|finnish|french|german|italian|japanese|mexican|new zealander|spanish|swedish|swiss)\b(?!\s+grand prix|\s+gp)",
     "A driver's nationality is in f1_drivers, as a word like British. JOIN f1_drivers USING (driver_id).",
     "Q: How many wins do Finnish drivers have?\nA: SELECT COUNT(*) FROM f1_results r JOIN f1_drivers d USING (driver_id) WHERE d.nationality = 'Finnish' AND r.position = 1"),
    (r"\blaps\b", "Laps completed is the laps column of f1_results.",
     "Q: How many laps did Kimi Raikkonen complete in 2005?\nA: SELECT SUM(laps) FROM f1_results WHERE driver_name = 'Kimi Räikkönen' AND season = 2005"),
    (r"\b(oldest|youngest)\b", "Age comes from f1_races.date and f1_drivers.dob. JOIN f1_races USING (season, round) and f1_drivers USING (driver_id).",
     "Q: Who was the youngest driver to finish on the podium?\nA: SELECT r.driver_name FROM f1_results r JOIN f1_races c USING (season, round) JOIN f1_drivers d USING (driver_id) WHERE r.position <= 3 ORDER BY c.date - d.dob ASC LIMIT 1"),
    (r"\bat (?!the\b)[A-Z]|\bcircuit\b", "f1_results has no circuit columns. JOIN f1_races USING (season, round). f1_races.circuit_id is the lowercase circuit name.",
     "Q: Which driver won the most races at Hockenheim?\nA: SELECT r.driver_name, COUNT(*) AS wins FROM f1_results r JOIN f1_races c USING (season, round) WHERE c.circuit_id = 'hockenheimring' AND r.position = 1 GROUP BY r.driver_name ORDER BY wins DESC LIMIT 1"),
]

# The dataset has none of this, so Python refuses without asking the model.
NOT_IN_DATA = re.compile(r"\b(weather|rain|rainfall|temperature|tyres?|tires?|lap times?|favou?rite|popular|opinions?"
                         r"|engineers?|sponsors?|salary|salaries|contracts?|budgets?|attendance|penalt(y|ies)|overtak(es?|ing)"
                         r"|design(s|ed|er|ers)?|owns|owned|owners?"
                         # race-day details the results tables never record
                         r"|safety cars?|virtual safety car|vsc|red flags?|driver of the day|team radio|radio|drs|sector times?"
                         r"|strateg(y|ies)|undercut|telemetry|downforce|horsepower|prize money|tickets?|spectators?|crowds?"
                         # measures and belongings no table holds
                         r"|top speeds?|speeds?|capacity|seating|weigh(s|t|ts)?|costs?|price[sd]?|money|colou?rs?|liver(y|ies)"
                         r"|fuel|followers|social media|instagram|helmets?)\b"
                         r"|\blaps\b.*\b(lead|led)\b|\b(lead|led)\b.*\blaps\b", re.IGNORECASE)

# SQL can only answer for things the tables hold, so these list what they hold
HOW_MANY = re.compile(r"\bhow many (\w+)", re.IGNORECASE)
COUNTABLE = set("""race races grand grands sprint sprints win wins victory victories pole poles podium podiums point points driver drivers
    constructor constructors team teams time times season seasons title titles championship championships lap laps pit
    stop stops round rounds circuit circuits country countries different distinct consecutive fastest start starts
    retirement retirements dnf dnfs finish finishes""".split())
WHO_ROLE = re.compile(r"^\s*who (?:is|was) (?:the|his|her|their) (\w+)", re.IGNORECASE)
ROLES = set("""winner champion first last youngest oldest fastest most best only leader runner second third driver
    drivers constructors world teammate""".split())
NO_MEASURE = re.compile(r"^\s*how (much|tall|heavy|big|long|fast|far)\b", re.IGNORECASE)
WHICH_THING = re.compile(r"^\s*which (\w+)", re.IGNORECASE)
CHOOSABLE = set("""driver drivers team teams constructor constructors race races grand circuit circuits track tracks
    season seasons year years round rounds country countries nationality""".split())


# "most" only, because "at least one" isn't a ranking
RANKED = re.compile(r"\b(?:most|biggest|largest) (\w+)", re.IGNORECASE)
RANKABLE = COUNTABLE | {"career", "successful", "recent", "often"}
FUTURE = re.compile(r"\b(will|going to)\b", re.IGNORECASE)
# "how many did they win" names no noun, so there is nothing to check
VERBS = set("did do does have has had were was are is will can could of".split())


def asks_for_missing_field(question: str) -> bool:
    """
    Checks on the shape of a question. An allow-list of nouns for "what" questions was tried and
    dropped: it refused "career tally" and "points haul" on new questions, so measures the tables
    lack are listed in NOT_IN_DATA instead.
    """
    counted, role, which = HOW_MANY.search(question), WHO_ROLE.search(question), WHICH_THING.search(question)
    if which is not None and which.group(1).lower() not in CHOOSABLE:
        return True  # which company, which engineer: the tables only pick drivers, teams, races and places
    if FUTURE.search(question):
        return True  # a prediction
    if any(word.lower() not in RANKABLE for word in RANKED.findall(question)):
        return True  # most Instagram followers
    counted_word = counted.group(1).lower() if counted else None
    # pit stop durations are the one length the tables hold
    return ((NO_MEASURE.search(question) is not None and not re.search(r"\bpit stops?\b", question, re.IGNORECASE))
            or (counted_word is not None and counted_word not in COUNTABLE and counted_word not in VERBS)
            or (role is not None and role.group(1).lower() not in ROLES and not role.group(1).isdigit()))


def build_prompt(question: str):
    """Returns the prompt, or None when the question needs data we don't have."""
    if NOT_IN_DATA.search(question):
        return None
    matched = [(note, example) for pattern, note, example in HINTS
               if re.search(pattern, question, flags=0 if "[A-Z]" in pattern else re.IGNORECASE)]
    notes = "\n".join(note for note, _ in matched)
    examples = "\n\n".join(example for _, example in matched)
    return "\n\n".join(part for part in (BASE_PROMPT, notes, examples) if part)


NO_SQL = "NO_SQL"
# Values a correct query can use without the question saying them
SAFE_WORDS = {"grand", "prix", "finished", "lapped"}
SAFE_NUMBERS = {0, 1, 2, 3}
# Switch off to measure what the check adds
USE_VALUE_GUARD = True

def clean_sql(text: str) -> str:
    """Pull one statement out of the model's reply. Multi-line SQL is kept."""
    text = text.replace("```sql", "").replace("```", "").strip()
    match = re.search(r"\b(SELECT|WITH)\b", text, flags=re.IGNORECASE)
    if match is None:
        return NO_SQL  # an English refusal is a refusal, not a parser error
    return text[match.start():].split(";")[0].split("\n\n")[0].strip()


def resolve_prompt(prompt, question: str):
    """A prompt is either fixed text or a function that builds one for the question."""
    return prompt(question) if callable(prompt) else prompt


def generate_sql(question: str, prompt=build_prompt) -> str:
    text = resolve_prompt(prompt, question)
    if text is None:
        return NO_SQL
    response = client.chat(
        model=MODEL,
        messages=[{"role": "user", "content": f"{text}\n\nQ: {question}\nA:"}],
        options=LLM_OPTIONS,
    )
    return clean_sql(response["message"]["content"])


def execute_sql(sql: str) -> tuple:
    """
    Execute SQL against DuckDB. Returns (dataframe, error).
    """
    try:
        result = con.execute(sql).df()
        return result, None
    except Exception as e:
        return None, str(e)


def fix_sql(question: str, sql: str, error: str, prompt=build_prompt) -> str:
    """Show the model its own failed query and what was wrong with it."""
    message = f"""{resolve_prompt(prompt, question)}

The query below failed. Return one corrected SELECT statement and nothing else.

Q: {question}
Failed SQL: {sql}
Error: {error.splitlines()[0]}
A:"""
    response = client.chat(
        model=MODEL,
        messages=[{"role": "user", "content": message}],
        options=LLM_OPTIONS,
    )
    return clean_sql(response["message"]["content"])


def words(text: str) -> list:
    """Lowercase words with accents removed, so Raikkonen matches Räikkönen."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", plain.lower())


def invented_values(sql: str, question: str) -> list:
    """
    Names and numbers in the SQL that the question never mentioned. The model copies
    example values into filters, and those queries run fine, so only this catches them.
    """
    asked = set(words(question))
    allowed_numbers = {int(n) for n in re.findall(r"\d+", question)} | SAFE_NUMBERS
    for decade in re.findall(r"\b(\d{3})0s\b", question):
        allowed_numbers |= set(range(int(decade) * 10, int(decade) * 10 + 10))

    invented = []
    for literal in re.findall(r"'((?:[^']|'')*)'", sql):
        terms = [w for w in words(literal) if w not in SAFE_WORDS]
        # hockenheimring is fine for "Hockenheim", so a long question word can be a prefix
        known = any(t in asked or any(len(a) >= 5 and t.startswith(a) for a in asked) for t in terms)
        if terms and not known:
            invented.append(literal)

    bare_sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    bare_sql = re.sub(r"\bLIMIT\s+\d+", "", bare_sql, flags=re.IGNORECASE)
    for number in re.findall(r"(?<![\w.])\d+(?![\w.])", bare_sql):
        if int(number) not in allowed_numbers:
            invented.append(number)
    # 1 is a safe number for wins and poles, but a round filter needs asking for
    if "round" not in asked:
        invented += re.findall(r"\bround\s*=\s*\d+", bare_sql, flags=re.IGNORECASE)
    return invented


def run_sql(question: str, prompt=build_prompt, max_retries: int = 2) -> dict:
    """Generate, check and execute, feeding problems back up to max_retries times."""
    sql = generate_sql(question, prompt)
    attempts = 1
    while True:
        if sql == NO_SQL:
            return {"sql": sql, "df": None, "error": None, "attempts": attempts}
        invented = invented_values(sql, question) if USE_VALUE_GUARD else []
        if invented:
            df, error = None, f"These values are not in the question, so remove those filters: {invented}"
        else:
            df, error = execute_sql(sql)
        if error is None or attempts > max_retries:
            return {"sql": sql, "df": df, "error": error, "attempts": attempts}
        sql = fix_sql(question, sql, error, prompt)
        attempts += 1


def numbers_in(text: str) -> set:
    return {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def sql_answer(question: str, result_df) -> str:
    """
    Turn the result into a sentence. Python handles empty results, and any answer
    containing a number the data doesn't contain is replaced by the raw rows.
    """
    if result_df is None or result_df.empty:
        return "The query returned no rows, so I can't answer that."

    result_text = result_df.head(20).to_string(index=False)
    prompt = f"""Answer the question in one sentence using only the data below.
Use the numbers exactly as shown. Do not add any fact or number that is not in the data.

Question: {question}

Data:
{result_text}

Answer:"""

    response = client.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        options=LLM_OPTIONS,
    )
    answer = response["message"]["content"].strip()

    allowed = numbers_in(result_text) | numbers_in(question)
    if not numbers_in(answer) <= allowed:
        return f"Result of the query:\n{result_text}"
    return answer
