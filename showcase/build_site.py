"""
Write showcase/site/data.js from the recorded answers and the frozen holdout results.

Run from the repo root after showcase/record.py:
    python showcase/build_site.py

The page reads a script, not a JSON file, so it also opens straight from disk.
"""
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "showcase" / "site"

# (split, label, who wrote the questions)
HOLDOUTS = [("holdout", "Holdout 1", "me"), ("holdout2", "Holdout 2", "me"), ("holdout3", "Holdout 3", "me"),
            ("holdout4", "Holdout 4", "me"), ("holdout5", "Holdout 5", "blind"), ("holdout6", "Holdout 6", "blind"),
            ("holdout7", "Holdout 7", "blind"), ("holdout8", "Holdout 8", "blind")]
# Oldest first. The page lists the newest first, so the demo examples and the blind sets lead
SET_LABELS = {"dev": "Development", "test": "Test 1", "test2": "Test 2", "test3": "Test 3", "test4": "Test 4",
              "final": "Final", **{split: label for split, label, _ in HOLDOUTS}, "examples": "Demo examples"}


def tally(rows: list, pipeline: str) -> dict:
    return {k: sum(r[pipeline] == k for r in rows) for k in ("right", "wrong", "refused")}


def frozen_scores() -> list:
    """Each holdout as it was scored once, on the code frozen before its questions were written."""
    scores = []
    for split, label, author in HOLDOUTS:
        if not (REPO / "eval" / f"results_{split}_new.json").exists():
            continue  # a set whose run hasn't finished
        rows = json.loads((REPO / "eval" / f"results_{split}_new.json").read_text(encoding="utf-8"))["rows"]
        base = json.loads((REPO / "eval" / f"results_{split}_baseline.json").read_text(encoding="utf-8"))["rows"]
        scores.append({"split": split, "label": label, "author": author, "total": len(rows),
                       **{p: tally(rows, p) for p in ("hybrid", "vector", "sql")},
                       "baseline": tally(base, "hybrid")})
    return scores


def main():
    recorded = json.loads((REPO / "showcase" / "answers.json").read_text(encoding="utf-8"))
    rows = recorded["rows"]
    data = {"recorded": recorded["recorded"], "commit": recorded["commit"], "sets": SET_LABELS,
            "holdouts": frozen_scores(), "paths": dict(Counter(r["path"] for r in rows)), "answers": rows}
    SITE.mkdir(exist_ok=True)
    (SITE / "data.js").write_text("window.SHOWCASE = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
                                  encoding="utf-8")
    print(f"wrote {SITE / 'data.js'}: {len(rows)} answers, {len(data['holdouts'])} holdouts")


if __name__ == "__main__":
    main()
