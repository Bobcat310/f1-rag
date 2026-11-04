# F1 RAG

A question-answering system over Formula 1 data from 1950 to 2026. It combines text-to-SQL with hybrid retrieval behind a keyword router, and it runs entirely on a laptop CPU at no cost: no paid APIs, no GPU and no framework.

Each part is built without a framework so it can be measured on its own, and each notebook builds on what the one before it measured.

**Result:** on 30 new questions, the system answered 27 correctly and gave 3 wrong answers, up from 23 right and 7 wrong for the same questions on its earlier version.

## How it works

```mermaid
flowchart TD
    Q[Question] --> R{Keyword router}
    R -->|topic not in the data| X[Refuse]
    R -->|fits a known shape| T[Python-filled SQL]
    R -->|one exact answer| S[Text-to-SQL]
    R -->|open question| V[Fused retrieval]
    S --> G{Value guard}
    G -->|invented value, retry| S
    G -->|passes| D[(DuckDB)]
    D -->|usable result| A1[Sentence from rows, number check]
    D -->|error, empty or lone zero| V
    V --> C[(Chroma + BM25)]
    C --> A2[Answer from top 5 sentences]
```

| Part | What it does | Code |
|---|---|---|
| Router | Regex rules choose a path and refuse topics the data doesn't cover | `src/router.py` |
| Templates | Parse fixed question shapes and fill the SQL in Python, with no model | `src/templates.py` |
| Text-to-SQL | Short prompt, plus only the hints this question needs | `src/text_to_sql.py` |
| Value guard | Rejects SQL containing names or numbers the question never mentioned | `src/text_to_sql.py` |
| Retrieval | Dense and BM25 search merged with reciprocal rank fusion | `src/retriever.py` |
| Live data | Pulls the current season from the Jolpica API and merges it | `src/live_data.py` |
| Extra data | Adds 612 sprint results and 12,913 pit stops from the same API | `src/extra_data.py` |
| Corpus | Turns 26,269 result rows, the standings and summaries of each race, driver, team and circuit into 32,555 sentences | `src/text_gen.py` |

## Results

The latest evaluation used 30 questions written after the code was committed, with live 2026 data through round 18. The same questions ran through the earlier version and the current code, so the two can be compared directly.

| Pipeline | Right | Wrong | Refused |
|---|---|---|---|
| Earlier hybrid | 23 | 7 | 0 |
| SQL only | 12 | 9 | 9 |
| Vector only | 19 | 5 | 6 |
| **Current hybrid** | **27** | 3 | 0 |

| Question type | SQL | Vector | Hybrid |
|---|---|---|---|
| Single fact (8) | 4 | 6 | 7 |
| Aggregate (9) | 3 | 2 | 9 |
| Narrative (7) | 0 | 6 | 6 |
| Unanswerable (6) | 5 | 5 | 5 |

Templates answered 13 of the 30 without the model. Each of the four gains traces to a change made after the previous set: a template for average pit stop time that leaves out red flag stoppages, refusing questions about owners, and returning a pinned overview or circuit sentence as written. The three wrong answers led to fixes made after this run, which no evaluation has scored yet: a podium the model misread, a season paraphrased without its wins, and a "which company" question nothing refused.

Three earlier frozen sets of 30 rose from 14 right to 27, from 21 to 25 and from 20 to 26, each measuring an earlier round of changes.

Search alone found the answer sentence for 9 of 14 questions. With sentences pinned for the race, season, career or circuit a question names, the context held it for all 14.

Scoring checks that each answer contains the expected fact. The questions were written by the system's author and each ran once, so these scores show direction rather than a precise rate.

## Design decisions

**Sentences built from tables, not scraped text.** Every sentence comes from a database row, so retrieved context can be traced to its source. The cost is a corpus of near-identical sentences, which is hard on embeddings, so each race also gets one summary sentence naming its circuit, winner, pole sitter and podium.

**Templates before the model.** Who won, who was on pole and how many wins all follow fixed shapes, so Python parses them and fills the SQL. A template must account for every word of the question, and any word it doesn't recognise sends the question to the model instead.

**One team, however many names.** Early entries pair chassis and engine, so Cooper appears under 10 names and an exact match gave it 2 wins instead of 16. Names are grouped into teams for counts and rankings. Team Lotus, the 2010-2011 Lotus team and Lotus F1 stay separate, and a question about "Lotus" alone counts all three and says so.

**Overviews are derived, not retrieved from race rows.** 88% of the original corpus was per-car race results, so "Tell me about Niki Lauda" had no sentence to find. One sentence per driver, team and circuit now holds those totals, and the question's subject pins it into the context. An overview question gets that sentence back as written, because a paraphrase from the model can drop its main facts.

**Status, not position, says what happened.** Every result row has a position, even a retirement, so sentences are built from `status`. That turns a misleading "finished 20th" into "retired (Collision)".

**Two paths, not one.** Notebook 4 showed retrieval can't answer "most wins for Ferrari in the 2000s": no single sentence holds a total. Notebook 5 showed SQL can't summarise a driver's season. Each path covers the other's weakness.

**BM25 fused with dense search.** In these sentences, exact names and years matter more than meaning. On a 34-hit retrieval test, dense search scored 15, BM25 28 and fusion 29. Reciprocal rank fusion uses ranks alone, so the two score scales never need calibrating.

**A keyword router, not an LLM.** Regex rules are instant, free, testable and explainable. An LLM router would put a slow step in front of every question.

**Definitions live in Python.** Pole position is `grid = 1`, because `f1_qualifying` starts in 1994 and gives Senna 3 poles instead of 65. A small semantic layer adds that hint only when the question needs it.

**Guards in code, not in the prompt.** Python refuses topics the data lacks, allows `how many` only for things the tables count, rejects invented values and verifies numbers in the final sentence. These checks behave the same way every time, and most bad queries run without error, so only a check outside the model catches them.

**Replace the whole season, in one transaction.** The 2026 calendar changed from 22 to 23 rounds while the snapshot was stale, so appending would have kept wrong rows. Rounds already stored must match the API, or the merge stops. A full index rebuild takes minutes and can't leave the corpus and Chroma out of step.

**Freeze the code, then write the test.** Each evaluation's questions were committed after the code and before any run, so the history shows nothing was tuned on them. Comparing versions on the same new questions keeps the gain measurable.

## What I'd do next

1. Refuse "what is the X" questions in Python when the tables hold no X. 12 of 47 unanswerable questions, such as top speeds and grandstand capacity, still reach the model.
2. Add lap-by-lap data from the same API to answer questions about laps led.
3. Test a larger local model on new questions.

## Run it

You need Python 3.12 and [Ollama](https://ollama.com). Download the Kaggle dataset "Formula 1 Complete History" and put its 8 CSVs in `data/raw/`.

```bash
python -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
ollama pull llama3.2:3b
```

Run these notebooks in order to build the data:

1. `01_schema_and_sql` loads the CSVs into DuckDB.
2. `02_text_generation` writes the corpus.
3. `04_naive_rag` builds the Chroma index.
4. `07_jolpica_live_data` adds the current season. It's safe to run again.

Then add sprints and pit stops with `python -m src.extra_data` and fix source names with `python -m src.clean_data`. Both are safe to repeat. Run notebook 07 once more to rewrite the corpus and index with them.

Then ask a question from the repo root:

```python
from src.router import ask

result = ask("Who won the 2021 Abu Dhabi Grand Prix?")
print(result["path"], result["answer"])
```

Set `F1_OLLAMA_URL` if Ollama isn't at `http://localhost:11434`. Run the checks with:

```bash
python tests/test_templates.py
python tests/test_literal_guard.py
python tests/test_live_data.py
python tests/test_text_gen.py
```

Score a question set with SQL only, vector only and the hybrid. `--code` points at another checkout to score an earlier version on the same questions:

```bash
python eval/run_holdout.py holdout4 eval/results_holdout4_new.json
```

## Repo layout

| Path | Contents |
|---|---|
| `notebooks/` | The project in order, one concept each (see below) |
| `src/` | Reusable pipeline code |
| `tests/` | Plain Python checks, including real SQL the model produced |
| `eval/` | 228 questions across 10 sets, every recorded result, and the runner that scores a set |

| Notebook | Topic | Main finding |
|---|---|---|
| 01 | Schema and SQL | The dataset's real columns differ from classic Ergast |
| 02 | Rows to sentences | 28,315 sentences from structured data |
| 03 | Embeddings | Cosine similarity by hand and a UMAP of the corpus |
| 04 | Naive RAG | Vocabulary mismatch and coverage gaps |
| 05 | Text-to-SQL | Selected hints beat long prompts |
| 06 | Hybrid router | BM25 gave retrieval its biggest gain |
| 06b | Value guard | Hybrid beats retrieval for the first time |
| 07 | Live data | 15 more rounds of 2026 through a validated merge |
| 08 | Final evaluation | Retrieval, generation and end-to-end scored separately |

Notebooks 05 to 08 record their own runs, and `src/` and the corpus changed afterwards, so re-running them gives different numbers. The latest results are in `eval/results_holdout4_*.json`.

## Stack

DuckDB for analytical SQL, ChromaDB for vectors, `rank_bm25` for keyword search, `all-MiniLM-L6-v2` for embeddings and Ollama with `llama3.2:3b` for generation. Data comes from Kaggle and the free [Jolpica API](https://api.jolpi.ca/ergast/f1/).
