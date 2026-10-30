"""API HTTP via TestClient."""

import pytest

from conftest import requires_bpy

pytestmark = requires_bpy


@pytest.fixture
def client(engine, out_dir):
    from fastapi.testclient import TestClient

    from blender_buildings.api import create_app

    return TestClient(create_app(engine))


def test_health_presets_schema(client):
    assert client.get("/health").json()["ok"]
    assert client.get("/presets").json()["presets"]
    assert client.get("/presets/house").json()["use"] == "residential"
    assert client.get("/presets/nope").status_code == 404
    assert "properties" in client.get("/schema").json()
    assert client.get("/materials").json()["materials"]


def test_metrics_without_engine(client):
    r = client.post("/metrics", json={"preset": "office", "overrides": {"floors": 2}})
    assert r.status_code == 200 and r.json()["metrics"]["floors"] == 2
    assert client.post("/metrics", json={}).status_code == 422
    assert client.post("/metrics", json={"preset": "nope"}).status_code == 422


def test_build_render_export_files(client, out_dir):
    r = client.post("/build", json={"preset": "mixed_use", "overrides": {"floors": 4}})
    assert r.status_code == 200 and r.json()["faces"] > 100
    r = client.post("/render", json={"engine": "workbench", "width": 160, "height": 100})
    assert r.status_code == 200
    f = client.get(r.json()["url"])
    assert f.status_code == 200 and f.headers["content-type"] == "image/png"
    r = client.post("/export", json={"format": "obj", "name": "mixte"})
    assert r.json()["size_bytes"] > 1000
    names = [x["name"] for x in client.get("/files").json()["files"]]
    assert any(n.endswith(".obj") for n in names)
    assert client.get("/files/../../etc/passwd").status_code == 404
    assert client.get("/files/missing.png").status_code == 404


def test_street_block_scene_reset(client):
    r = client.post("/street", json={"preset": "house", "count": 2, "seed": 1, "floors_range": [1, 2], "width_range": [10, 12]})
    assert r.status_code == 200 and len(r.json()["buildings"]) == 2
    r = client.post("/block", json={"buildings": [{"preset": "house"}, {"preset": "retail", "overrides": {"position": [40, 0, 0]}}]})
    assert r.status_code == 200
    assert client.get("/scene").json()["object_count"] >= 2
    assert client.post("/reset").json()["reset"]
    assert client.get("/scene").json()["object_count"] == 0


def test_validation_and_python(client, monkeypatch):
    assert client.post("/build", json={"preset": "house", "overrides": {"floors": 0}}).status_code == 422
    assert client.post("/python", json={"code": "result = 6 * 7"}).json()["result"] == 42
    monkeypatch.setenv("BLENDER_BUILDINGS_ALLOW_PYTHON", "0")
    assert client.post("/python", json={"code": "result = 1"}).status_code == 403
