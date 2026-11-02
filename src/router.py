"""Keyword router and the single ask() entry point, moved from notebook 06."""
import re

import pandas as pd

from src.retriever import fused_search, sentences
from src.templates import focus_lines, template_answer
from src.text_to_sql import LLM_OPTIONS, MODEL, NO_SQL, NOT_IN_DATA, asks_for_missing_field, client, run_sql, sql_answer


NARRATIVE = re.compile(r"^\s*(tell me|describe|explain|why|how did|how was|compare|summari[sz]e|what happened)", re.IGNORECASE)
FACT = re.compile(r"\b(how many|who|which|most|average|total|what is the|fastest|oldest|youngest)\b", re.IGNORECASE)


def route(question: str) -> str:
    """refuse: data we don't have. vector: open questions. sql: one exact answer."""
    if NOT_IN_DATA.search(question) or asks_for_missing_field(question):
        return "refuse"
    if NARRATIVE.search(question):
        return "vector"
    if FACT.search(question):
        return "sql"
    return "vector"


def answer_from_context(question: str, found: list) -> str:
    """Generation alone. Passing the right sentence here tests the model without retrieval."""
    context = "\n".join(f"- {sentence}" for sentence in found)
    prompt = f"""Answer the question in one or two sentences using ONLY the context below.
Never guess or infer beyond the context. If the context does not state the answer, reply exactly: Not in the context.

Context:
{context}

Question: {question}
Answer:"""
    response = client.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        options=LLM_OPTIONS,
    )
    return response["message"]["content"].strip()


def find_context(question: str, k: int = 5) -> list:
    """Sentences about a race the question names go first, because every car's result looks alike to search."""
    starts = tuple(focus_lines(question))
    pinned = [s for s in sentences if s.startswith(starts)] if starts else []
    return (pinned + [s for s in (sentences[i] for i in fused_search(question, k)) if s not in pinned])[:k]


def answer_vector(question: str) -> tuple:
    found = find_context(question)
    return answer_from_context(question, found), found


def usable(run: dict) -> bool:
    """A failed, empty or zero result is no evidence. A count of 0 usually means a bad filter."""
    if run["sql"] == NO_SQL or run["error"] or run["df"].empty:
        return False
    if run["df"].shape == (1, 1):
        value = run["df"].iloc[0, 0]
        return bool(pd.notna(value)) and value != 0
    return True


def answer_sql_only(question: str) -> str:
    run = run_sql(question)
    return sql_answer(question, run["df"]) if usable(run) else "No usable result from the database."


def ask(question: str) -> dict:
    """The single entry point: choose a path, and fall back to retrieval if SQL gives nothing usable."""
    path = route(question)
    if path == "refuse":
        return {"path": path, "answer": "That isn't in the data.", "sql": None, "sources": []}
    fixed = template_answer(question)
    if fixed:
        return {"path": "template", "answer": fixed["answer"], "sql": fixed["sql"], "sources": []}
    if path == "sql":
        run = run_sql(question)
        if usable(run):
            return {"path": path, "answer": sql_answer(question, run["df"]), "sql": run["sql"], "sources": []}
        answer, sources = answer_vector(question)
        return {"path": "sql>vector", "answer": answer, "sql": run["sql"], "sources": sources}
    answer, sources = answer_vector(question)
    return {"path": path, "answer": answer, "sql": None, "sources": sources}
