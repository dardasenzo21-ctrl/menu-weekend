import pytest

from blender_buildings import BuildingSpec, compute_metrics, get_preset
from blender_buildings.metrics import format_metrics


def test_basic_numbers():
    s = BuildingSpec(name="T", floors=5, floor_height=3.0, footprint={"kind": "rect", "width": 20, "depth": 10}, ground_floor={"height": 4.0}, efficiency_ratio=0.8)
    m = compute_metrics(s)
    assert m["footprint_area_m2"] == 200
    assert m["perimeter_m"] == 60
    assert m["gross_floor_area_m2"] == 1000
    assert m["usable_area_m2"] == 800
    assert m["wall_height_m"] == 16
    assert m["facade_area_m2"] == 960
    assert 0 < m["glazing_ratio"] < 1
    assert m["estimated_units"] == int(800 / 65)
    assert m["unit_label"] == "logements"


def test_parcel_and_price():
    s = get_preset("haussmann", {"site.parcel_area": 500, "price_per_m2": 10000})
    m = compute_metrics(s)
    assert m["site_coverage_ratio"] == pytest.approx(252 / 500, abs=1e-3)
    assert m["density_ratio"] == pytest.approx(1512 / 500, abs=1e-3)
    assert m["estimated_value_eur"] == pytest.approx(m["usable_area_m2"] * 10000)
    txt = format_metrics(m)
    assert "CES" in txt and "Valeur estimée" in txt


def test_office_hotel_mixed_outputs():
    assert "estimated_workstations" in compute_metrics(get_preset("office"))
    h = compute_metrics(get_preset("hotel"))
    assert h["unit_label"] == "chambres"
    mx = compute_metrics(get_preset("mixed_use"))
    assert "estimated_units" in mx and "estimated_workstations" in mx


def test_window_counts_depend_on_style():
    base = {"floors": 3, "footprint": {"kind": "rect", "width": 30, "depth": 10}}
    none = compute_metrics(BuildingSpec(windows={"style": "none"}, ground_floor={"storefront": False}, **base))
    punched = compute_metrics(BuildingSpec(windows={"style": "punched"}, **base))
    curtain = compute_metrics(BuildingSpec(windows={"style": "curtain", "bay_width": 1.5}, **base))
    assert none["glazing_area_m2"] == 0 and none["window_count"] == 0
    assert punched["window_count"] == 2 * (10 + 10 + 3 + 3)  # 2 étages courants × travées
    assert curtain["glazing_ratio"] > punched["glazing_ratio"]


def test_roof_volume_increases_with_pitched_roofs():
    flat = compute_metrics(BuildingSpec(roof={"kind": "flat"}))
    hip = compute_metrics(BuildingSpec(roof={"kind": "hip", "height": 3}))
    mansard = compute_metrics(BuildingSpec(roof={"kind": "mansard"}))
    assert flat["volume_m3"] < hip["volume_m3"] < mansard["volume_m3"]
