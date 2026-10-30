#!/usr/bin/env bash
# Installation complète et reproductible :
#   1. Blender 5.2.3 LTS (binaire officiel, vérifié SHA-256)
#   2. Environnement Python 3.13 avec bpy (module Blender), MCP SDK, FastAPI, pytest
#   3. Le package blender-buildings (editable) + mcp-for-blender (serveur MCP officiel pour Blender GUI)
#
# Usage : scripts/setup.sh [--system] [--skip-blender] [--skip-venv]
#   --system        installe le binaire dans /opt/blender (sinon blender/vendor/blender)
#   --skip-blender  ne télécharge pas le binaire (le module pip bpy suffit en headless)
#   --skip-venv     ne touche pas à l'environnement Python
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BLENDER_VERSION="5.2.3"
BLENDER_SERIES="5.2"
SYSTEM=0; SKIP_BLENDER=0; SKIP_VENV=0
for a in "$@"; do
  case "$a" in
    --system) SYSTEM=1 ;;
    --skip-blender) SKIP_BLENDER=1 ;;
    --skip-venv) SKIP_VENV=1 ;;
    *) echo "argument inconnu : $a" >&2; exit 2 ;;
  esac
done

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

# --- bibliothèques système (Debian/Ubuntu, si root) -------------------------------------------
if [ "$(uname -s)" = "Linux" ] && command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = "0" ]; then
  log "Bibliothèques système (libEGL, libGL, X11, Xvfb)"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libegl1 libgl1 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libsm6 libxext6 libx11-6 libgomp1 xvfb curl xz-utils >/dev/null
fi

# --- binaire Blender -------------------------------------------------------------------------
if [ "$SKIP_BLENDER" = "0" ]; then
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) ASSET="blender-${BLENDER_VERSION}-linux-x64.tar.xz" ;;
    Darwin-arm64) ASSET="blender-${BLENDER_VERSION}-macos-arm64.dmg" ;;
    Darwin-x86_64) ASSET="blender-${BLENDER_VERSION}-macos-x64.dmg" ;;
    *) echo "Plateforme non gérée par ce script : $(uname -s)-$(uname -m). Télécharger Blender sur https://www.blender.org/download/" >&2; ASSET="" ;;
  esac
  if [ -n "$ASSET" ]; then
    DL="$HERE/vendor/downloads"; mkdir -p "$DL"
    if [ ! -f "$DL/$ASSET" ]; then
      log "Téléchargement de $ASSET (≈ 385 Mo)"
      curl -L --retry 4 --retry-delay 2 -o "$DL/$ASSET" "https://download.blender.org/release/Blender${BLENDER_SERIES}/${ASSET}"
    fi
    log "Vérification SHA-256"
    (cd "$DL" && grep " $ASSET\$" "$HERE/vendor/blender-${BLENDER_VERSION}.sha256" | sha256sum -c -)
    if [[ "$ASSET" == *.tar.xz ]]; then
      DEST="$HERE/vendor/blender"; [ "$SYSTEM" = "1" ] && DEST="/opt/blender"
      log "Extraction vers $DEST"
      mkdir -p "$DEST" && tar -xJf "$DL/$ASSET" -C "$DEST" --strip-components=1
      "$DEST/blender" --version | head -1
      export BLENDER_BIN="$DEST/blender"
    else
      log "Image macOS téléchargée : $DL/$ASSET — ouvrir le .dmg et glisser Blender dans /Applications"
    fi
  fi
fi

# --- environnement Python --------------------------------------------------------------------
if [ "$SKIP_VENV" = "0" ]; then
  cd "$HERE"
  PY=""
  for c in python3.13 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info[:2]==(3,13) else 1)'; then PY="$c"; break; fi
  done
  if [ -z "$PY" ]; then
    echo "Python 3.13 requis pour bpy 5.2 (https://www.python.org/downloads/ ou 'uv python install 3.13')." >&2
    if command -v uv >/dev/null 2>&1; then uv python install 3.13 && PY="$(uv python find 3.13)"; else exit 1; fi
  fi
  log "Environnement virtuel (.venv) avec $PY"
  if command -v uv >/dev/null 2>&1; then
    uv venv --python "$PY" .venv >/dev/null
    VIRTUAL_ENV="$HERE/.venv" uv pip install -e ".[all]" "vendor/mcp_for_blender-2.2.6-py3-none-any.whl"
  else
    "$PY" -m venv .venv
    .venv/bin/pip install --upgrade pip >/dev/null
    .venv/bin/pip install -e ".[all]" "vendor/mcp_for_blender-2.2.6-py3-none-any.whl"
  fi
  log "Diagnostic"
  .venv/bin/blender-buildings doctor 2>/dev/null || true
fi

log "Terminé. Essayer : .venv/bin/blender-buildings build --preset haussmann --out output/demo"
