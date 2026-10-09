# Security

## Reporting a vulnerability

Please report it privately, not in a public issue. Open the
[Security tab](https://github.com/stufently/aviasales-mcp/security) of this repository and use
**Report a vulnerability**
([direct link](https://github.com/stufently/aviasales-mcp/security/advisories/new)). If that
button is not available, open an issue asking for a private channel — without any details of
the problem.

## What the server touches

All thirteen tools are read-only: the server searches cached fares and reference data and never
books or buys anything.

- **One credential:** `AVIASALES_API_TOKEN`, your Travelpayouts API token. It is read from the
  environment and sent only to `api.travelpayouts.com`, in the `X-Access-Token` header. It is
  never put into a URL.
- **No local storage.** The server writes no files; the token lives wherever your MCP client
  config or `.env` keeps it.
- **Booking links** point to `www.aviasales.ru`. If you set `AVIASALES_PARTNER_ID`, it is added
  to those links as the `marker` parameter — that is what the partner ID is for, and it is
  visible to whoever opens the link.

`.env`, `.mcp.json`, `.claude/` and `.cursor/` are in this repo's `.gitignore`. In your own
projects, keep the token in the user-level client config rather than a committed project file.

## HTTP transport

Over stdio (the default) nothing listens on the network. With `MCP_PORT` set the server speaks
streamable HTTP, and anyone who reaches the port can spend your Travelpayouts quota:

- Set `MCP_AUTH_TOKEN`; every request then needs `Authorization: Bearer <token>`.
- The default bind is `127.0.0.1`. A non-loopback bind without `MCP_AUTH_TOKEN` refuses to start
  unless you also set `MCP_ALLOW_INSECURE_HTTP=true` — don't.
- Leave `MCP_AUTH_ALLOW_QUERY_TOKEN` off: a `?token=` in the URL ends up in uvicorn's and any
  proxy's access log.
- There is no TLS; terminate it at a reverse proxy.

## Least privilege

The server only reads the Data API, so it needs nothing beyond a token for it. If you can,
keep that token for this server alone, so it can be reissued in Travelpayouts without breaking
anything else.
