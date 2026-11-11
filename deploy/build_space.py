"""
Assemble the folder to upload as a Hugging Face Space: the app, src/, the Space files
and the data, which git ignores so it never reaches GitHub.

Run from the repo root: python deploy/build_space.py [output folder]
"""
import shutil
import sys
from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "deploy" / "build"

DATA = ["data/f1.db", "data/processed/corpus.txt"]


def check_data():
    """The index and the corpus must describe the same sentences, or search returns the wrong ones."""
    for path in DATA + ["chroma_db"]:
        if not (ROOT / path).exists():
            sys.exit(f"Missing {path}. Build the data first (see the README).")
    lines = sum(1 for _ in open(ROOT / "data/processed/corpus.txt", encoding="utf-8"))
    indexed = chromadb.PersistentClient(path=str(ROOT / "chroma_db")).get_collection("f1_corpus").count()
    if lines != indexed:
        sys.exit(f"corpus.txt has {lines} sentences but the index has {indexed}. Rebuild the index first.")
    print(f"data ok: {lines} sentences, all indexed")


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(ROOT / "deploy" / "space", OUT, ignore=ignore)
    shutil.copy2(ROOT / "app.py", OUT / "app.py")
    shutil.copytree(ROOT / "src", OUT / "src", ignore=ignore)
    for path in DATA:
        (OUT / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, OUT / path)
    shutil.copytree(ROOT / "chroma_db", OUT / "chroma_db")
    # start.sh runs in Linux, where a Windows line ending breaks every line
    start = OUT / "start.sh"
    start.write_bytes(start.read_bytes().replace(b"\r\n", b"\n"))
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"built {OUT} ({size:.0f} MB)")
    print(f"upload with: hf upload <your-username>/f1-rag \"{OUT}\" . --repo-type=space")


if __name__ == "__main__":
    check_data()
    build()
