"""Scène Blender : réinitialisation, sol, éclairage, caméra automatique, rendu. Nécessite ``bpy``."""

from __future__ import annotations

import math
import os
from typing import Any, Iterable, Literal

import bpy
from mathutils import Vector

from .materials import get_material

View = Literal["perspective", "iso", "front", "back", "left", "right", "top"]
Engine = Literal["workbench", "eevee", "cycles"]


def reset_scene() -> None:
    """Scène vide (pas de cube/caméra/lampe par défaut)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"


def ensure_ground(size: float = 120.0, material: str = "asphalt") -> Any:
    obj = bpy.data.objects.get("Ground")
    if obj is None:
        mesh = bpy.data.meshes.new("Ground")
        h = size / 2
        mesh.from_pydata([(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0)], [], [[0, 1, 2, 3]])
        mesh.update()
        obj = bpy.data.objects.new("Ground", mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.location.z = -0.01
    else:
        h = max(size / 2, abs(obj.data.vertices[0].co.x))
        for v, (sx, sy) in zip(obj.data.vertices, ((-1, -1), (1, -1), (1, 1), (-1, 1))):
            v.co = (sx * h, sy * h, 0)
    obj.data.materials.clear()
    obj.data.materials.append(get_material(material))
    return obj


def ensure_lighting(sun_elevation: float = 50.0, sun_azimuth: float = 160.0, strength: float = 3.0) -> None:
    scene = bpy.context.scene
    sun = bpy.data.objects.get("Sun")
    if sun is None:
        light = bpy.data.lights.new("Sun", "SUN")
        sun = bpy.data.objects.new("Sun", light)
        scene.collection.objects.link(sun)
    sun.data.energy = strength
    sun.data.angle = math.radians(2.0)
    sun.rotation_euler = (math.radians(90 - sun_elevation), 0.0, math.radians(sun_azimuth))
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0.66, 0.76, 0.90, 1.0)
        bg.inputs[1].default_value = 0.6


def _mesh_objects(names: Iterable[str] | None = None) -> list[Any]:
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.name != "Ground"]
    if names:
        wanted = set(names)
        objs = [o for o in objs if o.name in wanted]
    return objs


def scene_bounds(names: Iterable[str] | None = None) -> tuple[Vector, Vector]:
    objs = _mesh_objects(names)
    if not objs:
        return Vector((-5, -5, 0)), Vector((5, 5, 5))
    # Les objets fraîchement créés n'ont pas encore de matrix_world évaluée : forcer la mise à jour.
    bpy.context.view_layer.update()
    lo = Vector((math.inf,) * 3)
    hi = Vector((-math.inf,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(min(a, b) for a, b in zip(lo, w))
            hi = Vector(max(a, b) for a, b in zip(hi, w))
    return lo, hi


def frame_camera(view: View = "perspective", names: Iterable[str] | None = None, margin: float = 1.06, azimuth: float = 35.0, elevation: float = 22.0, focal_mm: float = 35.0) -> Any:
    """Crée/positionne la caméra pour cadrer les bâtiments. Vues orthographiques pour les élévations."""
    scene = bpy.context.scene
    cam_obj = bpy.data.objects.get("Camera")
    if cam_obj is None:
        cam = bpy.data.cameras.new("Camera")
        cam_obj = bpy.data.objects.new("Camera", cam)
        scene.collection.objects.link(cam_obj)
    cam = cam_obj.data
    scene.camera = cam_obj
    lo, hi = scene_bounds(names)
    center = (lo + hi) / 2
    size = hi - lo
    radius = max(size.length / 2, 1.0)
    cam.clip_end = max(1000.0, radius * 20)

    if view in ("perspective", "iso"):
        cam.type = "PERSP"
        cam.lens = focal_mm
        az = math.radians(azimuth if view == "perspective" else 45.0)
        el = math.radians(elevation if view == "perspective" else 35.264)
        direction = Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
        cam_obj.location = center + direction * (radius * 3)
        _look_at(cam_obj, center)
        # Distance minimale pour que les 8 coins de la boîte englobante tiennent dans le cadre.
        aspect = scene.render.resolution_x / scene.render.resolution_y
        fov = 2 * math.atan(cam.sensor_width / (2 * focal_mm))
        tan_h = math.tan(fov / 2) if aspect >= 1 else math.tan(fov / 2) * aspect
        tan_v = tan_h / aspect if aspect >= 1 else math.tan(fov / 2)
        rot = cam_obj.rotation_euler.to_matrix()
        right, up = rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0))
        dist = 1.0
        for sx in (lo.x, hi.x):
            for sy in (lo.y, hi.y):
                for sz in (lo.z, hi.z):
                    v = Vector((sx, sy, sz)) - center
                    along = v.dot(direction)
                    dist = max(dist, along + abs(v.dot(right)) / tan_h * margin, along + abs(v.dot(up)) / tan_v * margin)
        cam_obj.location = center + direction * dist
        _look_at(cam_obj, center)
    else:
        cam.type = "ORTHO"
        axes = {
            "front": (Vector((0, -1, 0)), (size.x, size.z)),
            "back": (Vector((0, 1, 0)), (size.x, size.z)),
            "left": (Vector((-1, 0, 0)), (size.y, size.z)),
            "right": (Vector((1, 0, 0)), (size.y, size.z)),
            "top": (Vector((0, 0, 1)), (size.x, size.y)),
        }
        direction, (w, h) = axes[view]
        aspect = scene.render.resolution_x / scene.render.resolution_y
        cam.ortho_scale = max(w, h * aspect) * margin
        cam_obj.location = center + direction * (radius * 4 + 10)
        if view == "top":
            cam_obj.rotation_euler = (0.0, 0.0, 0.0)
        else:
            _look_at(cam_obj, center)
    bpy.context.view_layer.update()  # matrix_world de la caméra à jour pour les appelants
    return cam_obj


def _look_at(obj: Any, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def configure_render(engine: Engine = "eevee", resolution: tuple[int, int] = (1280, 720), samples: int = 16, transparent: bool = False) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = transparent
    if engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = False
        scene.cycles.device = "CPU"
    elif engine == "eevee":
        scene.render.engine = "BLENDER_EEVEE_NEXT" if hasattr(bpy.types, "SceneEEVEE") and "BLENDER_EEVEE_NEXT" in _engine_ids() else "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = samples
        if hasattr(scene.eevee, "use_shadows"):
            scene.eevee.use_shadows = True
    else:
        scene.render.engine = "BLENDER_WORKBENCH"
        sh = scene.display.shading
        sh.light = "STUDIO"
        sh.color_type = "MATERIAL"
        sh.show_shadows = True
        sh.show_cavity = True
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.0
    except Exception:
        pass


def _engine_ids() -> set[str]:
    try:
        return {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    except Exception:
        return set()


def render_image(path: str, view: View = "perspective", engine: Engine = "eevee", resolution: tuple[int, int] = (1280, 720), samples: int = 16, names: Iterable[str] | None = None, **camera_kwargs: Any) -> dict[str, Any]:
    """Rend la scène vers ``path`` (PNG). Retourne un résumé."""
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    configure_render(engine, resolution, samples)
    ensure_lighting()
    frame_camera(view, names, **camera_kwargs)
    scene = bpy.context.scene
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return {"path": path, "engine": scene.render.engine, "view": view, "resolution": list(resolution), "size_bytes": os.path.getsize(path) if os.path.exists(path) else 0}


def scene_info() -> dict[str, Any]:
    scene = bpy.context.scene
    objs = []
    for o in scene.objects:
        item: dict[str, Any] = {"name": o.name, "type": o.type, "location": [round(c, 3) for c in o.location]}
        if o.type == "MESH":
            item["vertices"] = len(o.data.vertices)
            item["faces"] = len(o.data.polygons)
            item["materials"] = [m.name for m in o.data.materials if m]
            if "bb_use" in o:
                item["use"] = o["bb_use"]
        objs.append(item)
    lo, hi = scene_bounds()
    return {
        "blender": bpy.app.version_string,
        "file": bpy.data.filepath,
        "engine": scene.render.engine,
        "objects": objs,
        "object_count": len(objs),
        "collections": [c.name for c in bpy.data.collections],
        "bounds": {"min": [round(c, 2) for c in lo], "max": [round(c, 2) for c in hi]},
    }


def delete_objects(names: Iterable[str]) -> list[str]:
    removed = []
    for n in names:
        o = bpy.data.objects.get(n)
        if o is not None:
            mesh = o.data if o.type == "MESH" else None
            bpy.data.objects.remove(o, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            removed.append(n)
    return removed
