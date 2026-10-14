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

# Lets the image start with no token so directories (Glama, the MCP registry)
# can run `initialize` and `tools/list` on it. Not a key: a tool call made with
# it is refused by the API ("Unauthorized — check AVIASALES_API_TOKEN"). A real
# `-e AVIASALES_API_TOKEN=...` overrides it. Runtime stage only, so the test
# image still sees a missing token as missing.
ENV AVIASALES_API_TOKEN=introspection-placeholder-not-a-key

ENTRYPOINT ["aviasales-mcp"]
