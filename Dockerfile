FROM python:3.13-slim AS base

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

FROM base AS dev

RUN pip install --no-cache-dir ".[dev]"

COPY tests/ tests/

FROM base AS runtime

ENTRYPOINT ["aviasales-mcp"]
