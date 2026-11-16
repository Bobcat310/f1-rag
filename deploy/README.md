# Deploying the demo

> **Hosting note (November 2026):** Hugging Face now requires a PRO plan to host Gradio and Docker Spaces, even on the free CPU tier. The public page is therefore a static Space of recorded answers (see [Static showcase](#static-showcase)). The Docker setup below still works for a PRO account or any machine with Docker.

The demo is a Gradio app (`app.py`) built to run in a Hugging Face Docker Space on CPU, with Ollama and `llama3.2:3b` in the same container, so it's the same pipeline the evaluations measured.

## Run it locally first

With Ollama running and the data built:

```bash
python app.py
```

Then open http://127.0.0.1:7860. Templates and refusals answer at once. Answers that need the model took 28 to 40 seconds on a laptop CPU, including loading the model, and will likely be slower on the Space's 2 vCPUs.

## Deploy

1. Create a write token at https://huggingface.co/settings/tokens and log in:

   ```bash
   hf auth login
   ```

2. Create the Space (Docker, free CPU):

   ```bash
   hf repo create f1-rag --repo-type space --space-sdk docker
   ```

3. Assemble the upload folder. It checks that the corpus and the index match, then copies the app, `src/`, the Space files from `deploy/space/` and the data, which git ignores:

   ```bash
   python deploy/build_space.py
   ```

4. Upload it. Large files go through Hugging Face's storage automatically:

   ```bash
   hf upload <your-username>/f1-rag deploy/build . --repo-type=space
   ```

The Space then builds the image, which installs Ollama, the CPU build of torch and both models. That takes several minutes. Follow it in the Space's Logs tab.

To update it later, rerun steps 3 and 4.

## Notes

- **Sleep.** A free Space sleeps after about 48 hours without visitors and takes a minute or two to wake. Open it shortly before sharing the link.
- **One question at a time.** The app queues questions and allows 20 waiting, so a burst of visitors waits in line instead of slowing every answer.
- **Frozen data.** The Space never calls the Jolpica API. To show newer races, update the data locally, rebuild and upload again.
- **Read-only.** DuckDB is opened read-only, so SQL the model writes can't change the data.

## Files

| Path | Purpose |
|---|---|
| `app.py` | The Gradio app, at the repo root so it runs locally |
| `deploy/space/Dockerfile` | Python 3.12, Ollama 0.40.15, CPU torch, both models baked in |
| `deploy/space/start.sh` | Starts Ollama, waits for it, then runs the app |
| `deploy/space/README.md` | The Space's card, with the settings Hugging Face reads |
| `deploy/space/requirements-app.txt` | Runtime dependencies only |
| `deploy/build_space.py` | Builds `deploy/build/`, the folder to upload |

## Static showcase

Static Spaces are free. The page at https://huggingface.co/spaces/humzanoor310/f1-rag shows every eval question as the current code answered it, with its route, SQL and sources, plus the frozen holdout scores. It runs no model.

To refresh it after a code change or a new holdout, with Ollama running:

```bash
rm showcase/answers.jsonl             # record from scratch; keep it to resume an interrupted run
python showcase/record.py             # about 30 minutes for 325 questions on a laptop CPU
python showcase/build_site.py         # writes showcase/site/data.js
hf upload humzanoor310/f1-rag showcase/site . --repo-type=space
```

Open `showcase/site/index.html` straight from disk to check it first. A link like `#holdout7_21` opens one answer.
