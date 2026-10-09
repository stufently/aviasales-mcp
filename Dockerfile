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

# The official MCP registry pulls this label and refuses to list the image unless
# it matches the `name` in server.json. Change the two together.
LABEL io.modelcontextprotocol.server.name="io.github.stufently/aviasales-mcp" \
      org.opencontainers.image.source="https://github.com/stufently/aviasales-mcp" \
      org.opencontainers.image.description="MCP server for Aviasales/Travelpayouts flight price search" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

ENTRYPOINT ["aviasales-mcp"]
