"""blender-buildings — modélisation paramétrique de bâtiments pour Blender.

Trois façons de l'utiliser :

* **Python** : ``from blender_buildings import BuildingSpec, build_building`` (nécessite ``bpy``).
* **MCP** : ``blender-buildings-mcp`` (serveur Model Context Protocol, transport stdio ou HTTP).
* **HTTP** : ``blender-buildings-api`` (FastAPI).

Le cœur (``spec``, ``geometry``, ``metrics``, ``presets``) est du Python pur : il fonctionne sans Blender.
Les modules ``builder``, ``materials``, ``scene`` et ``exporters`` nécessitent ``bpy`` (module pip ou binaire Blender).
"""

from .spec import (
    Balconies,
    BlockSpec,
    BuildingSpec,
    Facade,
    Footprint,
    GroundFloor,
    Roof,
    Site,
    Windows,
)
from .metrics import compute_metrics
from .presets import PRESETS, get_preset, list_presets

__version__ = "1.0.0"

__all__ = [
    "Balconies",
    "BlockSpec",
    "BuildingSpec",
    "Facade",
    "Footprint",
    "GroundFloor",
    "Roof",
    "Site",
    "Windows",
    "PRESETS",
    "compute_metrics",
    "get_preset",
    "list_presets",
    "__version__",
]


def build_building(spec, **kwargs):
    """Construit un bâtiment dans la scène Blender courante (import paresseux de bpy)."""
    from .builder import build_building as _build

    return _build(spec, **kwargs)


def build_block(spec, **kwargs):
    """Construit un îlot / une rue de bâtiments dans la scène Blender courante."""
    from .builder import build_block as _build

    return _build(spec, **kwargs)
