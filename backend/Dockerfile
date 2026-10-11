# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf \
    PATH=/opt/venv/bin:$PATH
WORKDIR /app

FROM base AS builder
RUN python -m venv /opt/venv
COPY requirements.txt .
# CPU-only torch: ~200 MB instead of the multi-GB CUDA wheel PyPI serves by default.
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.4,<3" \
 && pip install -r requirements.txt

# Bake the model weights into the image so pods start without reaching
# huggingface.co. Keep these in sync with EMBEDDING_MODEL / RERANKER_MODEL.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
ARG RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN python -c "from huggingface_hub import snapshot_download as d; \
[d(m, allow_patterns=['*.json', '*.txt', '*.safetensors']) for m in ('${EMBEDDING_MODEL}', '${RERANKER_MODEL}')]" \
 && chmod -R a+rX /opt/hf

FROM base AS runtime
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf /opt/hf
COPY app ./app
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001
EXPOSE 8000
# One worker per container: the models live in process memory, so scale with replicas.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "30"]
