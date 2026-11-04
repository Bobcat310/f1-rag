"""
Score one question split with SQL only, vector only and the hybrid, using notebook 08's rules.

Run from the repo root:
    python eval/run_holdout.py holdout4 eval/results_holdout4_new.json

--code points at another checkout's root to score an earlier version on the same questions.
The questions always come from this repo, and both versions share data/ and chroma_db/.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

parser = argparse.ArgumentParser()
parser.add_argument("split")
parser.add_argument("out")
parser.add_argument("--code", default=str(REPO), help="root of the checkout whose src/ is scored")
args = parser.parse_args()
sys.path.insert(0, str(Path(args.code).resolve()))

from src import router  # noqa: E402
from src.retriever import bm25_search, dense_search, fused_search, sentences  # noqa: E402
from src.router import answer_vector, ask, usable  # noqa: E402
from src.text_to_sql import NO_SQL, con, numbers_in, run_sql, sql_answer  # noqa: E402

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


def retrieval_hits(questions: list) -> dict:
    searches = {"dense": lambda q: [sentences[i] for i in dense_search(q, 5)],
                "bm25": lambda q: [sentences[i] for i in bm25_search(q, 5)],
                "fused": lambda q: [sentences[i] for i in fused_search(q, 5)]}
    if hasattr(router, "find_context"):  # the five sentences the model sees, pinned ones first
        searches["context"] = router.find_context
    return {name: {q["id"]: any(holds_evidence(s, q) for s in search(q["question"])) for q in questions}
            for name, search in searches.items()}


def score(q: dict) -> dict:
    run = run_sql(q["question"])
    if run["sql"] == NO_SQL:
        sql_text = "That isn't in the database."
    elif usable(run):
        sql_text = sql_answer(q["question"], run["df"])
    else:
        sql_text = "No usable result from the database."
    vector_text = answer_vector(q["question"])[0]
    hybrid = ask(q["question"])
    return {"id": q["id"], "kind": q["kind"], "question": q["question"], "path": hybrid["path"],
            "sql": outcome(q, sql_text), "vector": outcome(q, vector_text), "hybrid": outcome(q, hybrid["answer"]),
            "generated_sql": run["sql"], "sql_answer": sql_text, "vector_answer": vector_text,
            "hybrid_answer": hybrid["answer"], "hybrid_sql": hybrid["sql"]}


def main():
    with open(REPO / "eval" / "questions.json", encoding="utf-8") as f:
        questions = [q for q in json.load(f) if q["split"] == args.split]
    assert questions, f"no questions in split {args.split}"
    print(f"{args.split}: {len(questions)} questions", dict(Counter(q["kind"] for q in questions)), flush=True)

    retrieval = retrieval_hits([q for q in questions if q.get("evidence")])
    for name, hits in retrieval.items():
        print(f"{name:<7} answer sentence in the top 5: {sum(hits.values())}/{len(hits)}", flush=True)

    rows = []
    for q in questions:
        rows.append(score(q))
        r = rows[-1]
        print(f"{r['id']} {r['kind']:<12} {r['path']:<10} S={r['sql']:<7} V={r['vector']:<7} H={r['hybrid']:<7} "
              f"{r['hybrid_answer'][:90]!r}", flush=True)

    print()
    for name in ("sql", "vector", "hybrid"):
        print(f"{name:<7} {tally(rows, name)}")
    for kind in dict.fromkeys(r["kind"] for r in rows):
        subset = [r for r in rows if r["kind"] == kind]
        print(f"{kind:<13} of {len(subset):>2}:", {n: tally(subset, n)["right"] for n in ("sql", "vector", "hybrid")})
    print("paths:", dict(Counter(r["path"] for r in rows)))

    Path(args.out).write_text(json.dumps({"rows": rows, "retrieval": retrieval}, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")


if __name__ == "__main__":
    main()
