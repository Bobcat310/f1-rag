"""Text-to-SQL path, moved from notebook 05. See that notebook for how it was evaluated."""
import os
import re
from pathlib import Path

import duckdb
import ollama

PROJECT_ROOT = Path(__file__).resolve().parent.parent

con = duckdb.connect(str(PROJECT_ROOT / "data" / "f1.db"), read_only=True)
client = ollama.Client(host=os.environ.get("F1_OLLAMA_URL", "http://localhost:11434"))

MODEL = "llama3.2:3b"
# temperature 0 and a fixed seed make runs repeatable
LLM_OPTIONS = {"temperature": 0, "seed": 42}


BASE_PROMPT = """Write one DuckDB SELECT statement. Return only the SQL.

f1_results (one row per driver per race): season, round, race_name, driver_id, driver_name, constructor, grid, position, points, status
position = 1 is a win. race_name looks like 'Monaco Grand Prix'.
Use the names and years from the question. Only filter on what the question asks for."""

# (when the question matches, the note to add, an example of the pattern)
HINTS = [
    (r"\bpodiums?\b", "A podium means position <= 3.",
     "Q: How many podiums did Graham Hill score?\nA: SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Graham Hill' AND position <= 3"),
    (r"\bpoles?\b", "A pole position means grid = 1.",
     "Q: How many pole positions did Jim Clark take?\nA: SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Jim Clark' AND grid = 1"),
    (r"\b(not finish|fail(ed)? to finish|retire|dnf)", "Not finishing means status <> 'Finished' AND status <> 'Lapped' AND status NOT LIKE '+%'.",
     "Q: How many races did Jean Alesi fail to finish in 1995?\nA: SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Jean Alesi' AND season = 1995 AND status <> 'Finished' AND status <> 'Lapped' AND status NOT LIKE '+%'"),
    (r"\bper season\b", "An average per season is SUM(points) / COUNT(DISTINCT season).",
     "Q: What is the average points scored by Williams per season?\nA: SELECT SUM(points) / COUNT(DISTINCT season) AS average FROM f1_results WHERE constructor = 'Williams'"),
    (r"\bpoints\b(?!.*per season)", "Total points means SUM(points), not COUNT(*).",
     "Q: Which constructor scored the most points in 1996?\nA: SELECT constructor, SUM(points) AS total FROM f1_results WHERE season = 1996 GROUP BY constructor ORDER BY total DESC LIMIT 1"),
    (r"\bconstructors? championship\b", "Use f1_constructor_standings: season, position, points, wins, constructor.",
     "Q: Which team won the 2011 constructors championship?\nA: SELECT constructor FROM f1_constructor_standings WHERE season = 2011 AND position = 1"),
    (r"\bdrivers? championship\b", "Use f1_driver_standings: season, position, points, wins, driver_id.",
     "Q: Who won the 2011 drivers championship?\nA: SELECT driver_id FROM f1_driver_standings WHERE season = 2011 AND position = 1"),
    (r"\b(oldest|youngest)\b", "Age comes from f1_races.date and f1_drivers.dob. JOIN f1_races USING (season, round) and f1_drivers USING (driver_id).",
     "Q: Who was the youngest driver to finish on the podium?\nA: SELECT r.driver_name FROM f1_results r JOIN f1_races c USING (season, round) JOIN f1_drivers d USING (driver_id) WHERE r.position <= 3 ORDER BY c.date - d.dob ASC LIMIT 1"),
    (r"\bat (?!the\b)[A-Z]|\bcircuit\b", "f1_results has no circuit columns. JOIN f1_races USING (season, round). f1_races.circuit_id is the lowercase circuit name.",
     "Q: Which driver won the most races at Hockenheim?\nA: SELECT r.driver_name, COUNT(*) AS wins FROM f1_results r JOIN f1_races c USING (season, round) WHERE c.circuit_id = 'hockenheimring' AND r.position = 1 GROUP BY r.driver_name ORDER BY wins DESC LIMIT 1"),
]

# The dataset has none of this, so Python refuses without asking the model.
NOT_IN_DATA = re.compile(r"\b(weather|rain|rainfall|temperature|tyres?|tires?|pit stops?|lap times?|favou?rite|popular|opinions?)\b", re.IGNORECASE)


def build_prompt_v3(question: str):
    """Returns the prompt, or None when the question needs data we don't have."""
    if NOT_IN_DATA.search(question):
        return None
    matched = [(note, example) for pattern, note, example in HINTS
               if re.search(pattern, question, flags=0 if "[A-Z]" in pattern else re.IGNORECASE)]
    notes = "\n".join(note for note, _ in matched)
    examples = "\n\n".join(example for _, example in matched)
    return "\n\n".join(part for part in (BASE_PROMPT, notes, examples) if part)


NO_SQL = "NO_SQL"

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


def generate_sql(question: str, prompt=build_prompt_v3) -> str:
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


def fix_sql(question: str, sql: str, error: str, prompt=build_prompt_v3) -> str:
    """Show the model its own failed query and DuckDB's error message."""
    message = f"""{resolve_prompt(prompt, question)}

The query below failed. Return one corrected SELECT statement and nothing else.

Q: {question}
Failed SQL: {sql}
DuckDB error: {error.splitlines()[0]}
A:"""
    response = client.chat(
        model=MODEL,
        messages=[{"role": "user", "content": message}],
        options=LLM_OPTIONS,
    )
    return clean_sql(response["message"]["content"])


def run_sql(question: str, prompt=build_prompt_v3, max_retries: int = 2) -> dict:
    """Generate and execute, feeding errors back up to max_retries times."""
    sql = generate_sql(question, prompt)
    attempts = 1
    while True:
        if sql == NO_SQL:
            return {"sql": sql, "df": None, "error": None, "attempts": attempts}
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
