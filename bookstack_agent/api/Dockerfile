FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency manifests first — installs deps without the project itself
# so this layer is only invalidated when pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project && \
    uv pip install "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0"

# Copy source then install the project package
COPY src/ ./src/
COPY bookstack_agent/ ./bookstack_agent/
RUN uv sync --frozen --no-dev --no-editable

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "bookstack_agent.api.main:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools"]
