"""Tests de construction du maillage (module bpy en processus)."""

import pytest

from conftest import requires_bpy

from blender_buildings import PRESETS, get_preset, BuildingSpec

pytestmark = requires_bpy


@pytest.fixture(autouse=True)
def _fresh_scene():
    from blender_buildings.scene import reset_scene

    reset_scene()
    yield


def _bbox_z(obj):
    from mathutils import Vector

    zs = [(obj.matrix_world @ Vector(c)).z for c in obj.bound_box]
    return min(zs), max(zs)


@pytest.mark.parametrize("name", list(PRESETS))
def test_build_each_preset(name):
    import bpy
    from blender_buildings.builder import build_building

    spec = get_preset(name)
    r = build_building(spec)
    obj = bpy.data.objects[r["object"]]
    assert r["faces"] > 50 and r["vertices"] > 50
    assert len(obj.data.polygons) == r["faces"]
    z0, z1 = _bbox_z(obj)
    assert z0 == pytest.approx(0.0, abs=1e-3)
    assert z1 == pytest.approx(spec.total_height(), abs=0.6)  # débords de toit / lucarnes tolérés
    assert set(r["materials"]) >= {spec.facade.material}
    used = {p.material_index for p in obj.data.polygons}
    assert len(used) == len(obj.data.materials)  # chaque slot est utilisé par au moins une face
    assert all(m is not None for m in obj.data.materials)
    assert obj.data.uv_layers
    assert obj["bb_spec"]


def test_mesh_is_sane():
    import bmesh
    import bpy
    from blender_buildings.builder import build_building

    r = build_building(get_preset("haussmann"))
    mesh = bpy.data.objects[r["object"]].data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    assert all(len(f.verts) >= 3 for f in bm.faces)
    degenerate = [f for f in bm.faces if f.calc_area() < 1e-8]
    assert not degenerate
    loose = [v for v in bm.verts if not v.link_faces]
    assert not loose
    bm.free()


@pytest.mark.parametrize("roof", ["flat", "parapet", "hip", "gable", "mansard"])
@pytest.mark.parametrize("kind", ["rect", "L", "U", "polygon"])
def test_roofs_on_all_footprints(roof, kind):
    import bpy
    from blender_buildings.builder import build_building

    fp = {"kind": kind}
    if kind == "polygon":
        fp["points"] = [(-10, -6), (10, -6), (12, 0), (10, 6), (-10, 6)]
    spec = BuildingSpec(name=f"{kind}-{roof}", footprint=fp, roof={"kind": roof, "height": 3.0}, floors=3)
    r = build_building(spec)
    obj = bpy.data.objects[r["object"]]
    _, z1 = _bbox_z(obj)
    assert z1 >= spec.wall_height() - 1e-3


def test_position_rotation_and_collection():
    import bpy
    from blender_buildings.builder import build_building

    r = build_building(get_preset("house", {"position": (10, 5, 0), "rotation_deg": 30}))
    obj = bpy.data.objects[r["object"]]
    assert tuple(round(c, 3) for c in obj.location) == (10, 5, 0)
    assert obj.rotation_euler.z == pytest.approx(0.5236, abs=1e-3)
    assert obj.name in bpy.data.collections["Buildings"].objects
    assert bpy.data.objects.get("Ground") is not None


def test_street_and_block():
    import bpy
    from blender_buildings.builder import build_street, generate_street

    blk = generate_street({"preset": "haussmann", "count": 4, "seed": 5})
    assert len(blk.buildings) == 4
    xs = [b.position[0] for b in blk.buildings]
    assert xs == sorted(xs)
    r = build_street({"preset": "haussmann", "count": 4, "seed": 5})
    assert len(r["buildings"]) == 4
    assert r["total_gross_floor_area_m2"] > 0
    assert len(bpy.data.collections["Street"].objects) == 4


def test_same_seed_same_street():
    from blender_buildings.builder import generate_street

    a = generate_street({"preset": "office", "count": 3, "seed": 42}).model_dump()
    b = generate_street({"preset": "office", "count": 3, "seed": 42}).model_dump()
    c = generate_street({"preset": "office", "count": 3, "seed": 43}).model_dump()
    assert a == b and a != c


def test_window_styles_change_glass_faces():
    import bpy
    from blender_buildings.builder import build_building

    counts = {}
    for style in ("none", "punched", "ribbon", "curtain"):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        r = build_building(BuildingSpec(windows={"style": style, "bay_width": 2.0}, ground_floor={"storefront": False}, floors=3))
        obj = bpy.data.objects[r["object"]]
        glass_idx = [i for i, m in enumerate(obj.data.materials) if m and m.name.endswith("glass")]
        counts[style] = sum(1 for p in obj.data.polygons if p.material_index in glass_idx)
    assert counts["none"] == 0
    assert counts["punched"] > 0 and counts["ribbon"] > 0 and counts["curtain"] > 0


def test_materials_library():
    import bpy
    from blender_buildings.materials import get_material, list_materials

    names = [m["id"] for m in list_materials()]
    assert "limestone" in names and "glass" in names
    m1 = get_material("glass")
    m2 = get_material("glass")
    assert m1 is m2 and m1.use_nodes
    with pytest.raises(KeyError):
        get_material("marble")
    assert bpy.data.materials.get("BB_glass") is not None
