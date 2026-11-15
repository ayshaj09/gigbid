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
RUN pip install -e ".[models]" arq "pydantic[email]" sse-starlette langfuse && mkdir -p /app/data/processed && chown -R gigbid /app/data
USER gigbid
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
