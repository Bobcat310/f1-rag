"""Fused dense and BM25 retrieval, moved from notebook 06."""
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from src.text_to_sql import MODEL, client, words

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Unload the LLM first: on a machine short of memory the embedding model can't load beside it
client.generate(model=MODEL, keep_alive=0)

CORPUS_PATH = PROJECT_ROOT / "data" / "processed" / "corpus.txt"
with open(CORPUS_PATH, encoding="utf-8") as f:
    sentences = [line.strip() for line in f.readlines()]

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
collection = chromadb.PersistentClient(path=str(PROJECT_ROOT / "chroma_db")).get_collection("f1_corpus")


bm25 = BM25Okapi([words(s) for s in sentences])


def dense_search(query: str, k: int) -> list:
    query_vec = embedding_model.encode([query]).tolist()
    results = collection.query(query_embeddings=query_vec, n_results=k)
    return [int(i) for i in results["ids"][0]]


def bm25_search(query: str, k: int) -> list:
    scores = bm25.get_scores(words(query))
    return sorted(range(len(sentences)), key=lambda i: -scores[i])[:k]


def fused_search(query: str, k: int = 5, pool: int = 50, c: int = 60) -> list:
    """Reciprocal rank fusion: reward sentences ranked highly by either search."""
    fused = {}
    for ranked in (dense_search(query, pool), bm25_search(query, pool)):
        for position, sentence_id in enumerate(ranked):
            fused[sentence_id] = fused.get(sentence_id, 0) + 1 / (c + position + 1)
    return sorted(fused, key=lambda i: -fused[i])[:k]
