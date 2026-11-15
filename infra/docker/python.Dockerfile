# One image for api, worker and the MCP servers (different commands).
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN useradd -m gigbid
COPY pyproject.toml README.md ./
COPY agent agent
COPY rag rag
COPY mcp_servers mcp_servers
COPY apps/api apps/api
COPY apps/__init__.py apps/__init__.py
COPY worker worker
COPY evals evals
COPY dev dev
COPY data data
# INSTALL_MODELS=1 adds the open embedding + reranker models (CPU-only torch, ~1 GB RAM at runtime).
# Leave it 0 on small hosts (e.g. Render free, 512 MB) and set EMBEDDER_PROVIDER=hashing,
# RERANKER_PROVIDER=lexical there.
ARG INSTALL_MODELS=1
RUN if [ "$INSTALL_MODELS" = "1" ]; then       pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -e ".[models]";     else pip install -e .; fi  && pip install arq "pydantic[email]" sse-starlette langfuse  && mkdir -p /app/data/processed && chown -R gigbid /app/data
USER gigbid
EXPOSE 8000
# Hosts such as Render inject $PORT; default 8000 for docker compose.
CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
