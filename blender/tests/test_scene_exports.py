"""Rendu et exports (module bpy en processus)."""

import os

import pytest

from conftest import requires_bpy

from blender_buildings import get_preset

pytestmark = requires_bpy


@pytest.fixture(scope="module")
def built_scene():
    from blender_buildings.builder import build_building
    from blender_buildings.scene import reset_scene

    reset_scene()
    return build_building(get_preset("house"))


@pytest.mark.parametrize("fmt", ["glb", "gltf", "fbx", "obj", "stl", "usdc", "ply", "blend"])
def test_export_formats(built_scene, tmp_path, fmt):
    from blender_buildings.exporters import export_scene

    r = export_scene(str(tmp_path / f"house.{fmt}"), fmt)
    assert os.path.exists(r["path"])
    assert r["size_bytes"] > 500
    assert r["format"] == fmt


def test_export_bad_format(built_scene, tmp_path):
    from blender_buildings.exporters import export_scene

    with pytest.raises(ValueError):
        export_scene(str(tmp_path / "x.xyz"), "xyz")


@pytest.mark.parametrize("view", ["perspective", "iso", "front", "left", "top"])
def test_render_views_workbench(built_scene, tmp_path, view):
    from blender_buildings.scene import render_image

    r = render_image(str(tmp_path / f"{view}.png"), view=view, engine="workbench", resolution=(160, 100))
    assert os.path.exists(r["path"]) and r["size_bytes"] > 1000
    assert r["engine"] == "BLENDER_WORKBENCH"


def test_render_eevee_and_cycles(built_scene, tmp_path):
    from blender_buildings.scene import render_image

    r = render_image(str(tmp_path / "eevee.png"), engine="eevee", resolution=(96, 64), samples=2)
    assert "EEVEE" in r["engine"]
    r = render_image(str(tmp_path / "cycles.png"), engine="cycles", resolution=(64, 48), samples=1)
    assert r["engine"] == "CYCLES"


def test_camera_frames_whole_building(built_scene):
    import bpy
    from mathutils import Vector
    from blender_buildings.scene import frame_camera, scene_bounds, configure_render

    configure_render("workbench", (400, 300))
    cam = frame_camera("perspective")
    lo, hi = scene_bounds()
    corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    from bpy_extras.object_utils import world_to_camera_view

    for c in corners:
        u, v, d = world_to_camera_view(bpy.context.scene, cam, c)
        assert 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0 and d > 0


def test_scene_info_and_delete(built_scene):
    from blender_buildings.scene import delete_objects, scene_info

    info = scene_info()
    names = [o["name"] for o in info["objects"]]
    assert built_scene["object"] in names and "Ground" in names
    assert delete_objects([built_scene["object"], "nope"]) == [built_scene["object"]]
    assert built_scene["object"] not in [o["name"] for o in scene_info()["objects"]]


def test_save_and_open(tmp_path):
    from blender_buildings.builder import build_building
    from blender_buildings.exporters import open_blend, save_blend
    from blender_buildings.scene import reset_scene

    reset_scene()
    build_building(get_preset("retail"))
    p = save_blend(str(tmp_path / "s.blend"))
    reset_scene()
    r = open_blend(p["path"])
    assert "Commerce en pied d'immeuble" in r["objects"]
    with pytest.raises(FileNotFoundError):
        open_blend(str(tmp_path / "missing.blend"))


def test_camera_frames_offset_buildings():
    """Régression : les objets positionnés hors origine doivent compter dans le cadrage."""
    import bpy
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view
    from blender_buildings.builder import build_street
    from blender_buildings.scene import configure_render, frame_camera, reset_scene, scene_bounds

    reset_scene()
    build_street({"preset": "house", "count": 4, "seed": 2, "floors_range": [1, 2], "width_range": [10, 12], "gap": 5})
    lo, hi = scene_bounds()
    assert hi.x - lo.x > 50  # la rue est bien étendue
    configure_render("workbench", (640, 360))
    cam = frame_camera("perspective", azimuth=25, elevation=18)
    for x in (lo.x, hi.x):
        for y in (lo.y, hi.y):
            for z in (lo.z, hi.z):
                u, v, d = world_to_camera_view(bpy.context.scene, cam, Vector((x, y, z)))
                assert 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0 and d > 0
