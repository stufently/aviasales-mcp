FROM python:3.14-slim AS base

WORKDIR /app

# LICENSE is not decoration here: pyproject declares `license-files`, so the
# build fails without it and the installed package would carry no license text.
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

FROM base AS dev

RUN pip install --no-cache-dir ".[dev]"

COPY tests/ tests/

FROM base AS runtime

ENTRYPOINT ["aviasales-mcp"]
