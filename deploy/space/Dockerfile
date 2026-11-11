# Hugging Face Docker Space: Ollama and the Gradio app in one container, on the free CPU tier.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates zstd \
    && rm -rf /var/lib/apt/lists/*
# Pinned to the version the evaluations ran on
RUN curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION=0.40.15 sh

# Spaces run as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    OLLAMA_HOST=127.0.0.1:11434 \
    OLLAMA_MODELS=/home/user/ollama-models \
    OLLAMA_KEEP_ALIVE=-1 \
    HF_HOME=/home/user/hf-cache \
    GRADIO_ANALYTICS_ENABLED=False \
    F1_HOST=0.0.0.0 \
    F1_WARM_UP=1 \
    PORT=7860
WORKDIR /home/user/app

# The CPU build of torch is a fraction of the default CUDA one
RUN pip install --no-cache-dir --user torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
COPY --chown=user requirements-app.txt .
RUN pip install --no-cache-dir --user -r requirements-app.txt

# Bake both models into the image so a restart doesn't download them again
RUN ollama serve & \
    until curl -sf http://127.0.0.1:11434/api/tags > /dev/null; do sleep 1; done; \
    ollama pull llama3.2:3b
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY --chown=user . .
EXPOSE 7860
CMD ["bash", "start.sh"]
