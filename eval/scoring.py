"""
Notebook 08's scoring rules, shared by the holdout runner and the showcase recorder.

Import this after putting the checkout to score on sys.path, since it reads that checkout's src/.
"""
import re

from src.text_to_sql import con, numbers_in

REFUSAL = re.compile(r"(not|isn't) in the (context|database|data)|no usable result|no information|no data|"
                     r"cannot (provide|answer|determine)|can't answer|not mentioned|no .{0,30} mentioned|"
                     r"returned no rows|not provided|does not (state|contain|mention)", re.IGNORECASE)
NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def expected(q: dict) -> list:
    values = list(q.get("accept", []))
    if q["truth_sql"]:
        values.insert(0, con.execute(q["truth_sql"]).fetchone()[0])
    return values


def text_has(answer: str, value) -> bool:
    if isinstance(value, str):
        return value.lower() in answer.lower()
    found = numbers_in(answer) | {NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", answer.lower()) if w in NUMBER_WORDS}
    return any(abs(n - float(value)) <= 0.01 for n in found)


def outcome(q: dict, answer: str) -> str:
    """right, refused, or wrong. A wrong answer is the worst result, because it looks true."""
    refused = bool(REFUSAL.search(answer))
    values = expected(q)
    if not values:
        return "right" if refused else "wrong"
    if refused:
        return "refused"
    if answer.startswith("Result of the query:"):  # raw rows: only the top row is the answer
        lines = answer.splitlines()
        answer = lines[2] if len(lines) > 2 else ""
    return "right" if any(text_has(answer, v) for v in values) else "wrong"


def tally(rows: list, name: str) -> dict:
    return {k: sum(r[name] == k for r in rows) for k in ("right", "wrong", "refused")}


def holds_evidence(sentence: str, q: dict) -> bool:
    """Holdout evidence lists alternatives, each a set of terms one sentence must hold together."""
    options = q["evidence"] if isinstance(q["evidence"][0], list) else [q["evidence"]]
    return any(all(term in sentence for term in terms) for terms in options)
