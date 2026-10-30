#!/usr/bin/env bash
# Lance Blender + l'add-on officiel MCP for Blender SANS écran physique (Xvfb), port 9876.
# L'add-on refuse le mode `blender -b` : on lui donne un écran virtuel à la place.
# Ensuite, côté client MCP : `uvx mcp-for-blender` (ou .venv/bin/blender-mcp) se connecte au port 9876.
#
# Usage : scripts/run-blender-mcp-headless.sh [port]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-9876}"
BLENDER_BIN="${BLENDER_BIN:-}"
for c in "$BLENDER_BIN" "$HERE/vendor/blender/blender" /opt/blender/blender "$(command -v blender || true)"; do
  if [ -n "$c" ] && [ -x "$c" ]; then BLENDER_BIN="$c"; break; fi
done
[ -x "$BLENDER_BIN" ] || { echo "Blender introuvable (BLENDER_BIN)" >&2; exit 1; }
command -v xvfb-run >/dev/null || { echo "xvfb-run manquant : apt-get install xvfb" >&2; exit 1; }

"$HERE/scripts/install-blender-mcp-addon.sh" >/dev/null
START="$(mktemp)"
cat > "$START" <<PY
import bpy, os
bpy.ops.preferences.addon_enable(module="blender_mcp_addon")
bpy.context.scene.blendermcp_port = int(os.environ.get("BLENDER_PORT", "$PORT"))
bpy.ops.blendermcp.start_server()
print("MCP for Blender : serveur démarré sur le port", bpy.context.scene.blendermcp_port)
PY
export DISABLE_TELEMETRY=1 BLENDER_MCP_DISABLE_TELEMETRY=1 BLENDER_PORT="$PORT"
echo "Blender ($BLENDER_BIN) + add-on MCP sur le port $PORT (Ctrl-C pour arrêter)"
exec xvfb-run -a -s "-screen 0 1600x900x24" "$BLENDER_BIN" --python "$START"
