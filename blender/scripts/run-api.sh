#!/usr/bin/env bash
# API HTTP : http://127.0.0.1:8080/docs
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export BLENDER_BUILDINGS_OUTPUT="${BLENDER_BUILDINGS_OUTPUT:-$HERE/output}"
exec "$HERE/.venv/bin/blender-buildings-api" --host "${HOST:-127.0.0.1}" --port "${PORT:-8080}" "$@"
