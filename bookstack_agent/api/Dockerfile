FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock README.md ./

# Install main package deps (no dev extras) + FastAPI/uvicorn
RUN uv sync --frozen --no-dev --no-editable && \
    uv pip install "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0"

# Copy source
COPY src/ ./src/
COPY bookstack_agent/ ./bookstack_agent/

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "bookstack_agent.api.main:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools"]
