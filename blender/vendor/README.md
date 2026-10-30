# vendor/ — ce qui a été téléchargé

| Fichier | Source | Vérification |
|---|---|---|
| `blender-5.2.3.sha256` | https://download.blender.org/release/Blender5.2/blender-5.2.3.sha256 | sommes SHA-256 officielles (Linux, macOS, Windows) |
| `mcp_for_blender-2.2.6-py3-none-any.whl` | https://pypi.org/project/mcp-for-blender/2.2.6/ | sha256 `6f47cef6a5b5e2084269fcdec027fa8c6fb097157f1bf32cd922a711e59d738c` |
| `mcp_for_blender-2.2.6.tar.gz` | idem (sources) | sha256 `0b4f306804267be804cf315744aa55d010485dd6d919d4bb7270ec3f51b6efd9` |
| `blender_mcp_addon.py` | extrait de `mcp_for_blender-2.2.6.tar.gz` (`src/blender_mcp/bundled/addon.py`) | add-on Blender officiel du projet *MCP for Blender* (MIT, voir `LICENSE.mcp-for-blender`) |

Le binaire **Blender 5.2.3 LTS Linux x64** (`blender-5.2.3-linux-x64.tar.xz`, 385 Mo, sha256
`78486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec`) a été téléchargé et vérifié
pendant la mise en place, puis installé dans `/opt/blender`. Il n'est pas commité (trop gros pour git) :
`scripts/setup.sh` le retélécharge, le vérifie et l'installe dans `vendor/blender/` (ou `/opt/blender` avec `--system`).

Le module Python officiel `bpy==5.2.3` (Blender complet sans interface, ~300 Mo) est installé par `pip`
dans `.venv/` via `pip install -e ".[all]"`.
