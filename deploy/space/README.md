---
title: F1 RAG
emoji: 🏁
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Formula 1 Q&A from SQL and retrieval on a 3B model, on CPU
---

# F1 RAG

Ask questions about Formula 1 from 1950 to 2026. A keyword router sends each question to SQL filled in by Python, SQL written by the model, or fused keyword and semantic search over sentences built from the results tables. It refuses topics the data doesn't record.

Each answer shows the path it took, the SQL it ran and the sentences behind it.

It runs `llama3.2:3b` through Ollama on this Space's free CPU, so answers that need the model take a while. Answers filled in by Python templates and refusals come back at once.

Code, method and evaluation: https://github.com/Bobcat310/f1-rag

Data: the Kaggle dataset "Formula 1 Complete History" and the [Jolpica API](https://api.jolpi.ca/ergast/f1/), frozen at round 18 of 2026. Not affiliated with Formula 1.
