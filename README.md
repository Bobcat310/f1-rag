# F1 RAG

A question-answering system over Formula 1 data from 1950 to 2026. It combines text-to-SQL with hybrid retrieval behind a keyword router, and it runs entirely on a laptop CPU at no cost: no paid APIs, no GPU and no framework.

I built each part by hand so I could measure what it does, and each notebook starts from the failures of the one before it.

**Result:** on 30 new questions, the hybrid system answered 21 correctly, beating SQL alone (19) and retrieval alone (16). It also gave 5 confidently wrong answers, and most of this document is about why that happens and what reduced it.

## How it works

```mermaid
flowchart TD
    Q[Question] --> R{Keyword router}
    R -->|topic not in the data| X[Refuse]
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
| Text-to-SQL | Short prompt, plus only the hints this question needs | `src/text_to_sql.py` |
| Value guard | Rejects SQL containing names or numbers the question never mentioned | `src/text_to_sql.py` |
| Retrieval | Dense and BM25 search merged with reciprocal rank fusion | `src/retriever.py` |
| Live data | Pulls the current season from the Jolpica API and merges it | `src/live_data.py` |
| Corpus | Turns 26,269 result rows and the standings tables into 28,646 sentences | `src/text_gen.py` |

## Results

The final evaluation used 30 questions written after the code was committed, with live 2026 data through round 18.

| Pipeline | Right | Wrong | Refused |
|---|---|---|---|
| SQL only | 19 | 6 | 5 |
| Vector only | 16 | 4 | 10 |
| **Hybrid** | **21** | 5 | 4 |

| Question type | SQL | Vector | Hybrid |
|---|---|---|---|
| Single fact (10) | 8 | 4 | 7 |
| Aggregate (8) | 5 | 1 | 5 |
| Narrative (5) | 1 | 4 | 4 |
| Unanswerable (7) | 5 | 7 | 5 |

Scoring each stage separately shows where the failures come from:

| Stage | Score |
|---|---|
| Retrieval: answer sentence in the top 5 | Dense 7/15, BM25 8/15, fused 9/15 |
| Generation: model given the right sentence | 14/15 |

So retrieval limits the vector path, not the model. Four of the six retrieval misses are "who won" or "on pole" questions, because the corpus says "1st (winner)" and "starting from position 1".

Treat these as indicative. Thirty questions is a small sample, each ran once, and `temperature=0` turned out not to be fully repeatable. One valid refusal was also missed by the scorer, so hybrid is arguably 22 right and 4 wrong; the recorded score stays at 21.

## Design decisions

**Sentences built from tables, not scraped text.** Every sentence comes from a database row, so retrieved context can be traced to its source. The cost is a corpus of near-identical sentences, which is hard on embeddings.

**Two paths, not one.** Notebook 4 showed retrieval can't answer "most wins for Ferrari in the 2000s": no single sentence holds a total. Notebook 5 showed SQL can't summarise a driver's season. Each path covers the other's weakness.

**BM25 fused with dense search.** In these sentences, exact names and years matter more than meaning. On a 34-hit retrieval test, dense search scored 15, BM25 28 and fusion 29. Reciprocal rank fusion uses ranks alone, so the two score scales never need calibrating.

**A keyword router, not an LLM.** Regex rules are instant, free, testable and explainable. An LLM router would put a slow step in front of every question, using the same small model that already struggles with SQL.

**Definitions live in Python.** Pole position is `grid = 1`, because `f1_qualifying` starts in 1994 and gives Senna 3 poles instead of 65. A small semantic layer adds that hint only when the question needs it.

**Guards in code, not in the prompt.** After several rounds of prompt changes that each fixed one failure and caused another, the checks moved into Python: refuse topics the data lacks, reject invented values, and verify numbers in the final sentence. These behave the same way every time.

**Replace the whole season, in one transaction.** The 2026 calendar changed from 22 to 23 rounds while the snapshot was stale, so appending would have kept wrong rows. Rounds already stored must match the API, or the merge stops. A full index rebuild takes minutes and can't leave the corpus and Chroma out of step.

**Freeze the code, then write the test.** Questions are written after the code is committed, and old test sets are never used to tune. See the next section for why.

## What went wrong

The failures taught me the most, so they stay in the record.

**More prompt made it worse.** A longer prompt with more rules and examples dropped the score from 4/14 to 2/14. The small model copied example values, adding `circuit_id = 'monza'` to a career wins question. A short prompt with selected hints reached 7/14 on those same questions, which it had already seen, so that score is optimistic.

**My test sets were leaking.** The first prompt looked good because half of its test questions were also its few-shot examples: it scored 11/36 on unseen questions. A later score of 10/13 was inflated too, because I wrote the hints knowing the questions. The next clean test exposed it: the SQL path got 1 of 8 fact questions right.

**The first hybrid lost to plain retrieval,** 11/19 against 13/19. The router worked, but the SQL path dragged it down. That result led to the value guard, and hybrid first beat retrieval afterwards, 14/20 against 12/20.

**Silent failures are the real problem.** A retry loop added nothing, because most bad queries run without error. The value guard cut wrong answers from 6 to 4 on one test, at the cost of turning one right answer into a refusal. Queries using only the question's own words still pass it, such as `COUNT(DISTINCT race_name)` giving Alonso 17 wins instead of 32.

Scores from different notebooks use different questions, so they show direction, not a precise trend.

## Known limitations

- About one answer in six is confidently wrong. Don't rely on this system for facts without checking them.
- Fact-shaped unanswerable questions can reach SQL, which can't refuse them. "How many laps did Verstappen lead?" produced a nonsense answer.
- The value guard treats `1` as safe, so an invented `round = 1` passes.
- Some generated SQL came back with no `FROM`, costing a retry. It didn't reproduce, so the cause is unconfirmed.
- Vague questions like "Tell me about the 2026 Singapore Grand Prix" can miss the winner, because all 22 drivers' sentences look equally relevant.
- "Silverstone" isn't in the corpus, which only says "British Grand Prix".
- The router's rules were written alongside its labelled questions, so its 51/51 score isn't a clean one.

## What I'd do next

1. Add win-phrased sentences, such as "Max Verstappen won the 2021 Abu Dhabi Grand Prix", the likeliest fix for retrieval misses.
2. Use SQL templates filled by Python, with the model only choosing the template, to remove most wrong counts.
3. Test a larger local model on these same questions.
4. Add a cross-encoder reranker and circuit name aliases.

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

Then ask a question from the repo root:

```python
from src.router import ask

result = ask("Who won the 2021 Abu Dhabi Grand Prix?")
print(result["path"], result["answer"])
```

Set `F1_OLLAMA_URL` if Ollama isn't at `http://localhost:11434`. Run the checks with:

```bash
python tests/test_literal_guard.py
python tests/test_live_data.py
python tests/test_text_gen.py
```

## Repo layout

| Path | Contents |
|---|---|
| `notebooks/` | The project in order, one concept each (see below) |
| `src/` | Reusable pipeline code |
| `tests/` | Plain Python checks, including real SQL the model produced |
| `eval/` | 108 questions across 6 sets, plus every recorded result |

| Notebook | Topic | Main finding |
|---|---|---|
| 01 | Schema and SQL | The dataset's real columns differ from classic Ergast |
| 02 | Rows to sentences | 28,315 sentences from structured data |
| 03 | Embeddings | Cosine similarity by hand and a UMAP of the corpus |
| 04 | Naive RAG | Vocabulary mismatch and coverage gaps |
| 05 | Text-to-SQL | Selected hints beat long prompts |
| 06 | Hybrid router | BM25 helped most, but hybrid lost to retrieval |
| 06b | Value guard | Hybrid beats retrieval for the first time |
| 07 | Live data | 15 more rounds of 2026 through a validated merge |
| 08 | Final evaluation | Retrieval, generation and end-to-end scored separately |

Notebooks 05 and 06 record their own runs, and `src/` changed afterwards, so re-running them gives different numbers.

## Stack

DuckDB for analytical SQL, ChromaDB for vectors, `rank_bm25` for keyword search, `all-MiniLM-L6-v2` for embeddings and Ollama with `llama3.2:3b` for generation. Data comes from Kaggle and the free [Jolpica API](https://api.jolpi.ca/ergast/f1/).
