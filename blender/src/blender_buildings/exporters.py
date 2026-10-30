"""Export de la scène vers les formats courants (GLB/glTF, FBX, OBJ, STL, USD, PLY, .blend). Nécessite ``bpy``."""

from __future__ import annotations

import os
from typing import Any, Iterable

import bpy

FORMATS = ("glb", "gltf", "fbx", "obj", "stl", "usd", "usdc", "usda", "ply", "blend")


def _select(names: Iterable[str] | None) -> bool:
    """Sélectionne les objets demandés (ou tous les mesh). Retourne True si une sélection est active."""
    for o in bpy.context.scene.objects:
        o.select_set(False)
    if not names:
        return False
    for n in names:
        o = bpy.data.objects.get(n)
        if o is not None:
            o.select_set(True)
    return True


def export_scene(path: str, fmt: str | None = None, names: Iterable[str] | None = None, include_ground: bool = False) -> dict[str, Any]:
    """Exporte vers ``path``. Le format est déduit de l'extension si ``fmt`` est omis."""
    path = os.path.abspath(path)
    fmt = (fmt or os.path.splitext(path)[1].lstrip(".")).lower()
    if fmt not in FORMATS:
        raise ValueError(f"Format inconnu : {fmt!r}. Formats : {', '.join(FORMATS)}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not path.lower().endswith("." + fmt):
        path = f"{path}.{fmt}"

    if names is None and not include_ground:
        names = [o.name for o in bpy.context.scene.objects if o.name != "Ground" and o.type in ("MESH", "EMPTY")]
    selected = _select(names)

    if fmt in ("glb", "gltf"):
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB" if fmt == "glb" else "GLTF_SEPARATE", use_selection=selected, export_apply=True, export_yup=True)
    elif fmt == "fbx":
        bpy.ops.export_scene.fbx(filepath=path, use_selection=selected, apply_unit_scale=True, mesh_smooth_type="FACE", path_mode="COPY", embed_textures=False)
    elif fmt == "obj":
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=selected, export_materials=True, export_uv=True, export_normals=True)
    elif fmt == "stl":
        bpy.ops.wm.stl_export(filepath=path, export_selected_objects=selected)
    elif fmt in ("usd", "usdc", "usda"):
        bpy.ops.wm.usd_export(filepath=path, selected_objects_only=selected, export_materials=True)
    elif fmt == "ply":
        bpy.ops.wm.ply_export(filepath=path, export_selected_objects=selected)
    elif fmt == "blend":
        bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    return {"path": path, "format": fmt, "size_bytes": size, "objects": list(names or [])}


def save_blend(path: str) -> dict[str, Any]:
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return {"path": path, "size_bytes": os.path.getsize(path)}


def open_blend(path: str) -> dict[str, Any]:
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    bpy.ops.wm.open_mainfile(filepath=path)
    return {"path": path, "objects": [o.name for o in bpy.context.scene.objects]}
