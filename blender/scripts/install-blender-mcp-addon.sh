#!/usr/bin/env bash
# Installe l'add-on officiel « MCP for Blender » (vendor/blender_mcp_addon.py) dans Blender 5.2
# pour l'utiliser avec l'interface graphique : panneau latéral N > BlenderMCP > « Connect to Claude ».
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
case "$(uname -s)" in
  Darwin) DEST="$HOME/Library/Application Support/Blender/5.2/scripts/addons" ;;
  Linux)  DEST="${XDG_CONFIG_HOME:-$HOME/.config}/blender/5.2/scripts/addons" ;;
  *)      DEST="$APPDATA/Blender Foundation/Blender/5.2/scripts/addons" ;;
esac
mkdir -p "$DEST"
cp "$HERE/vendor/blender_mcp_addon.py" "$DEST/blender_mcp_addon.py"
echo "Add-on copié dans : $DEST/blender_mcp_addon.py"
echo "Dans Blender : Edit > Preferences > Add-ons > activer « Interface: MCP for Blender » (module blender_mcp_addon)."
