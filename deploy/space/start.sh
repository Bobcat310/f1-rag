#!/usr/bin/env bash
# Start Ollama, wait until it answers, then run the app in the foreground.
set -e
ollama serve > /tmp/ollama.log 2>&1 &
until curl -sf http://127.0.0.1:11434/api/tags > /dev/null; do sleep 1; done
exec python app.py
