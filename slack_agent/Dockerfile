FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Dependency layer — only invalidated when the manifests change
COPY slack_agent/pyproject.toml slack_agent/uv.lock ./
RUN uv sync --frozen --no-dev

COPY slack_agent/app.py ./

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uv", "run", "--no-sync", "python", "app.py"]
