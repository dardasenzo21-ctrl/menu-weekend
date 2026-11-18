"""Site réel à partir d'une adresse — testé hors ligne avec les réponses enregistrées (tests/fixtures/pasquier)."""

import json
import os

import pytest

from conftest import HAS_BPY

from blender_buildings import geo, geometry
from blender_buildings.metrics import compute_metrics

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "pasquier")


def _load(name: str) -> bytes:
    with open(os.path.join(FIX, name), "rb") as fh:
        return fh.read()


def make_fetcher(fail: set[str] = frozenset(), calls: list[str] | None = None):
    def fetch(url: str, headers=None, *args, **kwargs) -> bytes:
        if calls is not None:
            calls.append(url)
        for key, name in (("api-adresse", "ban.json"), ("nominatim", "nominatim.json"), ("BDTOPO", "bdtopo.json"), ("PARCELL", "parcelle.json"), ("interpreter", "osm.json"), ("wms", "wms.jpg")):
            if key in url:
                if key in fail:
                    raise RuntimeError(f"{key} indisponible (simulé)")
                return _load(name)
        raise AssertionError(f"URL inattendue : {url}")

    return fetch


def test_geocode_ban_then_nominatim():
    g = geo.geocode("8 rue Pasquier 75008 Paris", make_fetcher())
    assert g["source"].startswith("BAN") and abs(g["lat"] - 48.8717) < 1e-3
    g = geo.geocode("8 rue Pasquier 75008 Paris", make_fetcher(fail={"api-adresse"}))
    assert g["source"].startswith("Nominatim")
    with pytest.raises(RuntimeError):
        geo.geocode("x", make_fetcher(fail={"api-adresse", "nominatim"}))


def test_local_projection_is_metric_and_north_up():
    p = geo.LocalProjection(48.8716686, 2.3232457)
    assert p.to_local(2.3232457, 48.8716686) == pytest.approx((0.0, 0.0), abs=1e-6)
    x, y = p.to_local(2.3232457, 48.8716686 + 0.001)  # 1 millième de degré vers le nord ≈ 111 m
    assert abs(x) < 2.0 and 109 < y < 113


def test_lonlat_axis_order_heuristic():
    assert geo._lonlat([48.87, 2.32]) == (2.32, 48.87)
    assert geo._lonlat([2.32, 48.87]) == (2.32, 48.87)


def test_site_from_address_offline(tmp_path):
    calls: list[str] = []
    site = geo.site_from_address("8 rue Pasquier 75008 Paris", radius_m=60, ortho_dir=str(tmp_path), fetch=make_fetcher(calls=calls))
    t = site.target
    # Données IGN réelles : 7 niveaux, 20,7 m à l'égout, emprise ≈ parcelle de 119 m²
    assert t.floors == 7
    assert t.wall_height() == pytest.approx(20.7, abs=0.01)
    assert t.footprint.kind == "polygon" and len(t.footprint.points) == 4
    assert geometry.area(t.footprint.points) == pytest.approx(119.6, abs=1.0)
    assert site.parcel["area_m2"] == 119 and t.site.parcel_area == 119
    assert t.metadata["ign_levels"] == 7 and t.metadata["ign_usage"] == "Commercial et services"
    assert t.metadata["osm:id"] == "way/67559065"
    assert t.roof.kind == "mansard" and t.balconies.floors == [2, 6]
    # Voisins : volumétrie avec hauteurs IGN, dans le rayon, tous valides
    assert 10 <= len(site.context) <= 60
    assert all(c.footprint.kind == "polygon" and c.roof.kind == "parapet" for c in site.context)
    assert all(abs(c.position[0]) <= 60 + 1 and abs(c.position[1]) <= 60 + 1 for c in site.context)
    # Façade sur rue à l'ouest (rue Pasquier) → on la regarde depuis l'ouest (azimut ≈ 270°)
    assert 240 <= site.facade_azimuth_deg <= 290
    # Orthophoto écrite sur disque, extent cohérent
    assert site.ortho and os.path.exists(site.ortho.path) and site.ortho.half_size_m == 90
    assert any("BDTOPO" in u for u in calls) and any("wms" in u for u in calls)
    assert "IGN BD TOPO" in " ".join(site.sources)
    m = compute_metrics(t)
    assert m["gross_floor_area_m2"] == pytest.approx(119.6 * 7, abs=10)
    assert m["site_coverage_ratio"] == pytest.approx(1.0, abs=0.02)
    # Sérialisable / rechargeable
    again = geo.SiteModel.model_validate_json(site.model_dump_json())
    assert again.target == t


def test_site_degrades_gracefully_without_optional_sources(tmp_path):
    site = geo.site_from_address("8 rue Pasquier 75008 Paris", radius_m=40, ortho_dir=str(tmp_path), fetch=make_fetcher(fail={"api-adresse", "PARCELL", "interpreter", "wms"}))
    assert site.target.floors == 7
    assert site.parcel is None and site.ortho is None
    assert any("Parcelle" in n for n in site.notes) and any("Orthophoto" in n for n in site.notes)
    assert "osm:id" not in site.target.metadata


def test_overrides_apply_to_target(tmp_path):
    site = geo.site_from_address("8 rue Pasquier 75008 Paris", radius_m=30, orthophoto=False, osm=False, overrides={"facade.material": "brick_red", "roof.kind": "hip"}, fetch=make_fetcher())
    assert site.target.facade.material == "brick_red" and site.target.roof.kind == "hip"


def test_building_to_spec_handles_tall_single_level_halls():
    b = geo.GeoBuilding(id="halle", ring=[(0, 0), (30, 0), (30, 20), (0, 20)], height_m=19.9, levels=1)
    spec = geo.building_to_spec(b, "Halle", detailed=False)
    assert spec.floors >= 5 and spec.floor_height <= 12
    assert spec.wall_height() == pytest.approx(19.9, abs=0.01)


def test_building_to_spec_resplits_underestimated_levels():
    b = geo.GeoBuilding(id="x", ring=[(0, 0), (20, 0), (20, 15), (0, 15)], height_m=17.2, levels=2)
    spec = geo.building_to_spec(b, "X", detailed=False)
    assert spec.floors >= 5 and spec.floor_height <= 4.0
    assert spec.wall_height() == pytest.approx(17.2, abs=0.01)


def test_clean_ring_removes_closure_and_duplicates():
    ring = [(0, 0), (10, 0), (10, 0.1), (10, 10), (0, 10), (0, 0)]
    out = geo._clean_ring(ring)
    assert out[0] != out[-1] and len(out) == 4


@pytest.mark.skipif(not HAS_BPY, reason="module bpy absent")
def test_build_site_in_blender(tmp_path):
    import bpy

    from blender_buildings.builder import build_site
    from blender_buildings.scene import render_image, reset_scene, scene_bounds

    site = geo.site_from_address("8 rue Pasquier 75008 Paris", radius_m=50, ortho_dir=str(tmp_path), fetch=make_fetcher())
    reset_scene()
    r = build_site(site)
    assert r["context_count"] == len(site.context) and not r["context_errors"]
    assert r["ground"]["textured"] is True
    assert bpy.data.objects["Ground"].data.materials[0].node_tree.nodes.get("Image Texture") is not None
    lo, hi = scene_bounds()
    assert max(abs(lo.x), abs(lo.y), abs(hi.x), abs(hi.y)) < 120  # pas d'onglet parti à l'infini
    assert hi.z == pytest.approx(site.target.total_height(), abs=0.6)
    tgt = r["target"]["object"]
    out = render_image(str(tmp_path / "street.png"), view="street", engine="workbench", resolution=(120, 150), names=[tgt], azimuth=site.facade_azimuth_deg, street_distance=13)
    assert out["size_bytes"] > 500
    assert all(not o.hide_render for o in bpy.context.scene.objects)  # les voisins masqués sont restaurés
    out = render_image(str(tmp_path / "elev.png"), view="elevation", engine="workbench", resolution=(100, 100), names=[tgt], solo=True, azimuth=site.facade_azimuth_deg)
    assert out["size_bytes"] > 500
    cam = bpy.context.scene.camera
    assert cam.data.type == "ORTHO" and cam.location.x < -5  # caméra à l'ouest, face à la rue Pasquier
