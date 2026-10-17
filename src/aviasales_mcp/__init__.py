"""Aviasales MCP server package."""

import os

# fastmcp reads its own FASTMCP_* settings from `.env` in the working directory,
# which for a stdio server is whatever project the MCP client has open. A
# stranger's `.env` there could set FASTMCP_PORT=${AVIASALES_API_TOKEN} and
# have the token printed in the resulting traceback (verified). Point fastmcp
# at nothing unless the user named a file; this runs before fastmcp is imported
# because every entry point imports this package first.
os.environ.setdefault("FASTMCP_ENV_FILE", os.devnull)
