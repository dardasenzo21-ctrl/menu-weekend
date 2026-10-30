"""Matériaux PBR procéduraux (nœuds) pour Blender. Nécessite ``bpy``."""

from __future__ import annotations

import os
from typing import Any

import bpy

# nom -> (couleur RGB 0..1, rugosité, métallique, options)
_LIBRARY: dict[str, dict[str, Any]] = {
    "limestone": {"color": (0.78, 0.72, 0.60), "roughness": 0.85, "noise": 0.08, "scale": 2.0},
    "render_white": {"color": (0.90, 0.89, 0.86), "roughness": 0.80, "noise": 0.03, "scale": 4.0},
    "render_beige": {"color": (0.82, 0.74, 0.60), "roughness": 0.80, "noise": 0.04, "scale": 4.0},
    "concrete": {"color": (0.55, 0.55, 0.53), "roughness": 0.90, "noise": 0.10, "scale": 1.5},
    "brick_red": {"color": (0.55, 0.22, 0.16), "roughness": 0.85, "noise": 0.12, "scale": 8.0},
    "brick_dark": {"color": (0.28, 0.18, 0.15), "roughness": 0.85, "noise": 0.12, "scale": 8.0},
    "glass": {"color": (0.55, 0.72, 0.80), "roughness": 0.05, "metallic": 0.0, "transmission": 0.9, "alpha": 0.35},
    "glass_tinted": {"color": (0.18, 0.26, 0.32), "roughness": 0.05, "metallic": 0.3, "transmission": 0.5, "alpha": 0.6},
    "zinc": {"color": (0.45, 0.48, 0.52), "roughness": 0.45, "metallic": 0.6, "noise": 0.05, "scale": 3.0},
    "slate": {"color": (0.22, 0.24, 0.27), "roughness": 0.65, "noise": 0.06, "scale": 6.0},
    "terracotta_tile": {"color": (0.62, 0.32, 0.20), "roughness": 0.80, "noise": 0.08, "scale": 10.0},
    "metal_dark": {"color": (0.22, 0.23, 0.25), "roughness": 0.40, "metallic": 0.8},
    "metal_light": {"color": (0.80, 0.82, 0.84), "roughness": 0.45, "metallic": 0.7},
    "wood": {"color": (0.50, 0.34, 0.20), "roughness": 0.70, "noise": 0.15, "scale": 12.0},
    "corten": {"color": (0.45, 0.22, 0.12), "roughness": 0.85, "metallic": 0.2, "noise": 0.18, "scale": 3.0},
    "frame_black": {"color": (0.03, 0.03, 0.03), "roughness": 0.50, "metallic": 0.3},
    "frame_white": {"color": (0.92, 0.92, 0.90), "roughness": 0.45},
    "frame_bronze": {"color": (0.35, 0.25, 0.14), "roughness": 0.40, "metallic": 0.7},
    "asphalt": {"color": (0.16, 0.16, 0.16), "roughness": 0.95, "noise": 0.04, "scale": 0.5},
    "grass": {"color": (0.18, 0.32, 0.10), "roughness": 0.95, "noise": 0.10, "scale": 1.0},
    "stone_dark": {"color": (0.30, 0.30, 0.31), "roughness": 0.75, "noise": 0.06, "scale": 3.0},
}

PREFIX = "BB_"


def list_materials() -> list[dict[str, Any]]:
    return [{"id": k, "color": v["color"], "roughness": v.get("roughness", 0.5), "metallic": v.get("metallic", 0.0)} for k, v in _LIBRARY.items()]


def _set_input(node: Any, names: tuple[str, ...], value: Any) -> None:
    """Affecte une entrée du Principled BSDF en tolérant les renommages entre versions."""
    for n in names:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return


def get_material(name: str) -> Any:
    """Retourne (en le créant si besoin) le matériau nodal ``BB_<name>``."""
    if name not in _LIBRARY:
        raise KeyError(f"Matériau inconnu : {name!r}. Disponibles : {', '.join(_LIBRARY)}")
    full = PREFIX + name
    mat = bpy.data.materials.get(full)
    if mat is not None:
        return mat
    spec = _LIBRARY[name]
    mat = bpy.data.materials.new(full)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        out = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    color = tuple(spec["color"]) + (1.0,)
    _set_input(bsdf, ("Base Color",), color)
    _set_input(bsdf, ("Roughness",), spec.get("roughness", 0.5))
    _set_input(bsdf, ("Metallic",), spec.get("metallic", 0.0))
    if "transmission" in spec:
        _set_input(bsdf, ("Transmission Weight", "Transmission"), spec["transmission"])
        _set_input(bsdf, ("Alpha",), spec.get("alpha", 1.0))
        for attr, val in (("blend_method", "BLEND"), ("surface_render_method", "BLENDED")):
            if hasattr(mat, attr):
                try:
                    setattr(mat, attr, val)
                except Exception:
                    pass
    noise = spec.get("noise", 0.0)
    if noise > 0:
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = spec.get("scale", 2.0)
        tex.inputs["Detail"].default_value = 4.0
        coord = nodes.new("ShaderNodeTexCoord")
        links.new(coord.outputs["Object"], tex.inputs["Vector"])
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = float(noise) * 3.0
        mix.inputs[6].default_value = color  # A
        links.new(tex.outputs["Color"], mix.inputs[7])  # B
        links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = float(noise)
        links.new(tex.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    mat.diffuse_color = color  # couleur en vue solide / workbench
    mat.roughness = spec.get("roughness", 0.5)
    mat.metallic = spec.get("metallic", 0.0)
    return mat


def assign_materials(obj: Any, names: list[str]) -> None:
    """Crée les slots de matériaux de ``obj`` dans l'ordre de ``names``."""
    obj.data.materials.clear()
    for n in names:
        obj.data.materials.append(get_material(n))


def image_material(path: str, name: str | None = None, roughness: float = 0.9) -> Any:
    """Matériau à texture image (orthophoto plaquée sur le sol, par exemple)."""
    name = name or PREFIX + "img_" + os.path.basename(path)
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    img = bpy.data.images.get(os.path.basename(path)) or bpy.data.images.load(path)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF") or nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    _set_input(bsdf, ("Roughness",), roughness)
    _set_input(bsdf, ("Specular IOR Level", "Specular"), 0.1)
    mat.diffuse_color = (0.5, 0.5, 0.5, 1.0)
    return mat
