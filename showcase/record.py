"""
Record every eval question, plus the demo's examples, through the current ask(), for the static showcase.

Run from the repo root, with Ollama running:
    python showcase/record.py

It saves after every question to showcase/answers.jsonl and skips questions already recorded,
so an interrupted run picks up where it stopped. Delete that file to record from scratch.
"""
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "eval")]

from app import EXAMPLES  # noqa: E402
from scoring import expected, outcome  # noqa: E402
from src.router import ask  # noqa: E402

PROGRESS = REPO / "showcase" / "answers.jsonl"
OUT = REPO / "showcase" / "answers.json"


def plain(value):
    """DuckDB returns numpy and Decimal values, which JSON can't hold."""
    if isinstance(value, str) or value is None:
        return value
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)


def record(q: dict) -> dict:
    start = time.perf_counter()
    result = ask(q["question"])
    row = {"id": q["id"], "split": q["split"], "kind": q["kind"], "question": q["question"],
           "path": result["path"], "answer": result["answer"], "sql": result["sql"], "sources": result["sources"],
           "seconds": round(time.perf_counter() - start, 1)}
    if q["kind"] != "example":
        row["expected"] = [plain(v) for v in expected(q)]
        row["outcome"] = outcome(q, result["answer"])
    return row


def main():
    questions = json.loads((REPO / "eval" / "questions.json").read_text(encoding="utf-8"))
    questions += [{"id": f"example_{i + 1:02}", "split": "examples", "kind": "example", "question": text, "truth_sql": None}
                  for i, text in enumerate(EXAMPLES)]
    done = {}
    if PROGRESS.exists():
        done = {row["id"]: row for row in map(json.loads, PROGRESS.read_text(encoding="utf-8").splitlines())}
    with PROGRESS.open("a", encoding="utf-8") as progress:
        for n, q in enumerate(questions, 1):
            if q["id"] in done:
                continue
            row = record(q)
            done[q["id"]] = row
            progress.write(json.dumps(row, ensure_ascii=False) + "\n")
            progress.flush()
            print(f"{n}/{len(questions)} {row['seconds']:>5}s {row['path']:<10} {row.get('outcome', ''):<7} {q['question'][:70]}",
                  flush=True)

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    rows = [done[q["id"]] for q in questions]
    OUT.write_text(json.dumps({"recorded": date.today().isoformat(), "commit": commit, "rows": rows},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(rows)} answers, code at {commit})")


if __name__ == "__main__":
    main()
