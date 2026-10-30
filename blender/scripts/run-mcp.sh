#!/usr/bin/env bash
# Serveur MCP headless (stdio) — à référencer dans .mcp.json / claude_desktop_config.json.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export BLENDER_BUILDINGS_OUTPUT="${BLENDER_BUILDINGS_OUTPUT:-$HERE/output}"
exec "$HERE/.venv/bin/blender-buildings-mcp" "$@"
