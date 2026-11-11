"""
A small web demo over ask(). Run locally with Ollama running: python app.py

Each answer shows how it was reached: the path the router chose, the SQL and the
sentences behind it, so a wrong answer can be traced as easily as a right one.
"""
import html
import os
import threading
import time

import gradio as gr

from src.router import ask
from src.text_to_sql import LLM_OPTIONS, MODEL, client, con

REPO_URL = "https://github.com/Bobcat310/f1-rag"
MAX_QUESTION = 300

LAST_ROUND = con.execute("SELECT MAX(round) FROM f1_results WHERE season = (SELECT MAX(season) FROM f1_results)").fetchone()[0]
LAST_SEASON = con.execute("SELECT MAX(season) FROM f1_results").fetchone()[0]

# (label, what it means, where the SQL came from)
PATHS = {
    "template": ("Template", "Python recognised the question's shape and filled in the SQL. No language model was involved.",
                 "SQL filled in by Python"),
    "sql": ("Text-to-SQL", "The model wrote SQL, which passed the check for names and numbers the question never mentioned.",
            "SQL written by the model"),
    "sql>vector": ("Retrieval over SQL", "The model wrote SQL, but an answer drawn from the sentences below was preferred, "
                   "because every number in it must appear in sentences built from the tables.",
                   "SQL written by the model (not used)"),
    "vector": ("Retrieval", "Answered from the sentences below, found by keyword and semantic search.", ""),
    "refuse": ("Refused", "The question asks for something the data doesn't record, so the system declined instead of guessing.", ""),
}

EXAMPLES = [
    "Who won the 1997 European Grand Prix?",
    "Which team started from pole most often during the 2010s?",
    "How did Ferrari's 1979 season go?",
    "Compare Ayrton Senna and Alain Prost",
    "How many pit stops did Lewis Hamilton make in the 2021 British Grand Prix?",
    f"Who is leading the {LAST_SEASON} drivers championship?",
    "What was the weather like at the 2023 Monaco Grand Prix?",
]

INTRO = f"""
# F1 RAG

Ask about Formula 1 from 1950 to round {LAST_ROUND} of {LAST_SEASON}. A keyword router sends each question to
Python-filled SQL, model-written SQL or search over 32,000 sentences built from the results tables,
and refuses what the data doesn't hold. It runs a 3B model on a free CPU, with no paid APIs.

Every answer shows its route, SQL and sources. On 30 new questions written blind to the code,
it got 19 right, 9 wrong and refused 2, so check the sources. [Code, method and results]({REPO_URL})
"""

CSS = """
.route { border-left: 4px solid var(--color-accent); padding: 0.5rem 0.75rem; background: var(--block-background-fill); border-radius: 4px; }
.route .label { font-weight: 600; }
.sources ol { padding-left: 1.25rem; }
.sources li { margin-bottom: 0.35rem; }
"""


def respond(question: str):
    """Returns (answer, route, SQL, sources) for the four output components."""
    question = (question or "").strip()
    if not question:
        return "Type a question first.", "", gr.update(value="", visible=False), ""
    if len(question) > MAX_QUESTION:
        return f"Please keep questions under {MAX_QUESTION} characters.", "", gr.update(value="", visible=False), ""
    start = time.perf_counter()
    try:
        result = ask(question)
    except Exception:
        return "Something went wrong answering that one. Try rewording it.", "", gr.update(value="", visible=False), ""
    seconds = time.perf_counter() - start

    label, meaning, sql_label = PATHS.get(result["path"], (result["path"], "", "SQL"))
    route = (f'<div class="route"><span class="label">{label}</span> &middot; {seconds:.1f}s'
             f"<br>{html.escape(meaning)}</div>")
    sql = result.get("sql") or ""
    sources = result.get("sources") or []
    listed = ('<div class="sources"><b>Sentences behind this answer</b><ol>'
              + "".join(f"<li>{html.escape(s)}</li>" for s in sources) + "</ol></div>") if sources else ""
    return result["answer"], route, gr.update(value=sql, visible=bool(sql), label=sql_label), listed


def warm_up():
    """Load the model before the first visitor asks, so they don't wait for it."""
    try:
        client.generate(model=MODEL, prompt="Ready?", options=LLM_OPTIONS)
    except Exception:
        pass


with gr.Blocks(title="F1 RAG") as demo:
    gr.Markdown(INTRO)
    with gr.Row():
        question = gr.Textbox(label="Your question", placeholder="Who won the 2008 Brazilian Grand Prix?",
                              max_length=MAX_QUESTION, scale=5, autofocus=True)
        submit = gr.Button("Ask", variant="primary", scale=1)
    gr.Examples(EXAMPLES, inputs=question)
    answer = gr.Textbox(label="Answer", interactive=False, lines=3)
    route = gr.HTML()
    sql = gr.Code(label="SQL", language="sql", interactive=False, visible=False)
    sources = gr.HTML()
    gr.Markdown(f"Data from the Kaggle dataset \"Formula 1 Complete History\" and the "
                f"[Jolpica API](https://api.jolpi.ca/ergast/f1/), frozen at round {LAST_ROUND} of {LAST_SEASON}. "
                "Not affiliated with Formula 1. Answers come from a small model and can be wrong.")

    # One question at a time across both triggers: a second model call on a 2 CPU machine would slow both
    gr.on([submit.click, question.submit], respond, inputs=question, outputs=[answer, route, sql, sources],
          concurrency_limit=1, api_name="ask")


if __name__ == "__main__":
    if os.environ.get("F1_WARM_UP"):
        threading.Thread(target=warm_up, daemon=True).start()
    demo.queue(max_size=20).launch(server_name=os.environ.get("F1_HOST", "127.0.0.1"),
                                   server_port=int(os.environ.get("PORT", 7860)), css=CSS)
