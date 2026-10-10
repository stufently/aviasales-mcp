#!/usr/bin/env bash
# Build dist-mcpb/aviasales-mcp-<version>.mcpb.
# The only build entry point, locally and in CI. npm, the mcpb CLI, and uv
# run in Docker as the current user; nothing is installed on the host.
# `version` is read from pyproject.toml and is not stored in mcpb/manifest.json.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

NODE_IMAGE="node:24.21.0-slim"
UV_IMAGE="ghcr.io/astral-sh/uv:0.12.23-python3.14-trixie-slim"
MCPB_CLI="@anthropic-ai/mcpb@2.1.2"
OUT="dist-mcpb"
NPM_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/aviasales-mcp-mcpb-npm"
UV_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/aviasales-mcp-uv"
mkdir -p "$NPM_CACHE" "$UV_CACHE"
rm -rf "$OUT"
mkdir -p "$OUT"

VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cat >"$WORK/list_tools.py" <<'PY'
import asyncio
import json
import sys

from aviasales_mcp.server import mcp


async def main() -> None:
    tools = await mcp.list_tools()
    payload = [
        {"name": tool.name, "description": tool.description or ""} for tool in tools
    ]
    with open(sys.argv[1], "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


asyncio.run(main())
PY

cat >"$WORK/finish_manifest.py" <<'PY'
import json
import sys
import tomllib

stage, pyproject, source_manifest = sys.argv[1:]
version = tomllib.load(open(pyproject, "rb"))["project"]["version"]
manifest = json.load(open(source_manifest, encoding="utf-8"))
if "version" in manifest:
    sys.exit(f"{source_manifest}: version is substituted from pyproject.toml, do not store it")
live = json.load(open(f"{stage}/tools-list.json", encoding="utf-8"))
declared = [item.get("name") for item in manifest.get("tools") or []]
live_names = [item["name"] for item in live]
if set(declared) != set(live_names) or len(declared) != len(set(live_names)):
    missing = sorted(set(live_names) - set(declared))
    extra = sorted(set(declared) - set(live_names))
    sys.exit(f"tool names differ; missing {missing}; extra {extra}")
for item in live:
    if not str(item.get("description") or "").strip():
        sys.exit(f"tool {item.get('name')!r} has an empty description")
manifest["version"] = version
manifest["tools"] = [
    {"name": item["name"], "description": item["description"]} for item in live
]
with open(f"{stage}/manifest.json", "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2, ensure_ascii=False)
    handle.write("\n")
PY

cat >"$WORK/launch.py" <<'PY'
"""Desktop Extension entry point. The host runs this file with uv."""

from aviasales_mcp.server import main

if __name__ == "__main__":
    main()
PY

cat >"$WORK/mcpbignore" <<'EOF'
**/.git/**
**/__pycache__/**
**/*.pyc
**/.env
**/.env.*
**/.venv/**
**/tests/**
**/*.ts
**/*.tsx
**/*.mts
**/*.cts
tools-list.json
uv.lock
EOF

STAGE="$WORK/aviasales-mcp"
mkdir -p "$STAGE/src"
cp pyproject.toml README.md LICENSE "$STAGE/"
cp -a src/aviasales_mcp "$STAGE/src/aviasales_mcp"
cp "$WORK/launch.py" "$STAGE/launch.py"
cp "$WORK/mcpbignore" "$STAGE/.mcpbignore"

uid="$(id -u)"
gid="$(id -g)"

docker run --rm -u "$uid:$gid" -e HOME=/tmp \
  -e UV_CACHE_DIR=/cache \
  -e UV_PROJECT_ENVIRONMENT=/tmp/aviasales-venv \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e AVIASALES_API_TOKEN=dummy \
  -v "$UV_CACHE":/cache \
  -v "$STAGE":/ext \
  -v "$WORK/list_tools.py":/list_tools.py:ro \
  -w /ext \
  "$UV_IMAGE" \
  uv run --directory /ext python /list_tools.py /ext/tools-list.json

python3 "$WORK/finish_manifest.py" "$STAGE" pyproject.toml mcpb/manifest.json
rm -f "$STAGE/tools-list.json" "$STAGE/uv.lock"
rm -rf "$STAGE/.venv"
find "$STAGE" -type d -name __pycache__ -print0 | xargs -0r rm -rf

docker run --rm -u "$uid:$gid" -e HOME=/tmp -e npm_config_cache=/npm \
  -v "$NPM_CACHE":/npm \
  -v "$STAGE":/app \
  -v "$PWD/$OUT":/out \
  -w /app \
  "$NODE_IMAGE" \
  npx -y "$MCPB_CLI" pack /app "/out/aviasales-mcp-${VERSION}.mcpb"

test -f "$OUT/aviasales-mcp-${VERSION}.mcpb"
echo "built $OUT/aviasales-mcp-${VERSION}.mcpb"
