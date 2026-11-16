---
title: F1 RAG
emoji: 🏁
colorFrom: red
colorTo: gray
sdk: static
pinned: false
short_description: Recorded answers and blind-test scores from a local F1 RAG
---

# F1 RAG showcase

Every evaluation question run through the F1 RAG pipeline, with the route each answer took, the SQL it ran and the sentences behind it, plus how the system scored on frozen question sets.

The answers were recorded from the real pipeline (`llama3.2:3b` through Ollama on a laptop CPU), so this page doesn't run a model.

Code, method and evaluation: https://github.com/Bobcat310/f1-rag

Data: the Kaggle dataset "Formula 1 Complete History (1950–2026)", licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), and the [Jolpica API](https://api.jolpi.ca/ergast/f1/). Not affiliated with Formula 1.
