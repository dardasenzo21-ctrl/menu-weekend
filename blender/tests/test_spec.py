import json

import pytest
from pydantic import ValidationError

from blender_buildings import BuildingSpec, Footprint, PRESETS, get_preset, list_presets
from blender_buildings.spec import BlockSpec, StreetSpec, spec_json_schema


def test_defaults_roundtrip():
    s = BuildingSpec()
    data = json.loads(s.model_dump_json())
    assert BuildingSpec.model_validate(data) == s


@pytest.mark.parametrize("name", list(PRESETS))
def test_every_preset_is_valid(name):
    s = get_preset(name)
    assert s.floors >= 1
    assert len(s.footprint.polygon()) >= 4
    assert s.total_height() >= s.wall_height()


def test_list_presets_shape():
    items = list_presets()
    assert {"id", "name", "use", "description"} <= set(items[0])
    assert {i["id"] for i in items} == set(PRESETS)


def test_unknown_preset():
    with pytest.raises(KeyError):
        get_preset("nope")


def test_overrides_dotted_and_nested():
    s = get_preset("haussmann", {"floors": 8, "roof.kind": "hip", "facade": {"material": "brick_red"}})
    assert s.floors == 8
    assert s.roof.kind == "hip"
    assert s.facade.material == "brick_red"
    assert get_preset("haussmann").roof.kind == "mansard"  # le preset d'origine n'est pas modifié


def test_overrides_prune_out_of_range_floors():
    s = get_preset("mixed_use", {"floors": 4})  # balcons aux 2..6 dans le preset
    assert s.balconies.floors == [2, 3]
    h = get_preset("haussmann", {"floors": 3})  # corniches [1, 2, 5, 6]
    assert h.facade.cornice_floors == [1, 2]
    with pytest.raises(ValidationError):
        BuildingSpec(floors=4, balconies={"floors": [4]})  # sans surcharge : toujours strict


def test_footprint_polygons():
    assert len(Footprint(kind="rect").polygon()) == 4
    assert len(Footprint(kind="L").polygon()) == 6
    assert len(Footprint(kind="U").polygon()) == 8
    poly = Footprint(kind="polygon", points=[(0, 0), (0, 10), (10, 10)]).polygon()  # horaire → remis anti-horaire
    from blender_buildings.geometry import signed_area

    assert signed_area(poly) > 0 and len(poly) == 3


@pytest.mark.parametrize(
    "bad",
    [
        {"floors": 0},
        {"floor_height": 1.0},
        {"windows": {"width": 4.0, "bay_width": 3.0}},
        {"windows": {"sill": 2.0, "height": 2.0}, "floor_height": 3.0},
        {"balconies": {"floors": [9]}},
        {"footprint": {"kind": "polygon", "points": [(0, 0), (1, 1)]}},
        {"footprint": {"kind": "L", "wing_width": 50}},
        {"name": "   "},
        {"facade": {"material": "marble"}},
        {"unknown_field": 1},
    ],
)
def test_invalid_specs(bad):
    with pytest.raises(ValidationError):
        BuildingSpec.model_validate(bad)


def test_floor_levels_and_heights():
    s = BuildingSpec(floors=4, floor_height=3.0, ground_floor={"height": 4.0}, roof={"kind": "parapet", "parapet_height": 1.0})
    assert s.floor_levels() == [0.0, 4.0, 7.0, 10.0]
    assert s.wall_height() == 13.0
    assert s.total_height() == 14.0
    assert BuildingSpec(floors=1, roof={"kind": "gable", "height": 3}).total_height() == 4.0 + 3


def test_schema_has_fields():
    schema = spec_json_schema()
    assert "footprint" in schema["properties"]
    assert "$defs" in schema and "Roof" in schema["$defs"]


def test_street_and_block_specs():
    st = StreetSpec(count=3)
    assert st.floors_range == (5, 7)
    with pytest.raises(ValidationError):
        StreetSpec(width_range=(30, 10))
    with pytest.raises(ValidationError):
        BlockSpec(buildings=[])
