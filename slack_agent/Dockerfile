FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Copy dependency manifests first — installs deps without the project itself
# so this layer is only invalidated when pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --group slack-agent --no-install-project

# Copy source then install the project package
COPY src/ ./src/
COPY slack_agent/ ./slack_agent/
RUN uv sync --frozen --no-dev --group slack-agent --no-editable

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uv", "run", "--no-sync", "python", "-m", "slack_agent.app"]
