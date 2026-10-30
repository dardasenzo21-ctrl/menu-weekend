import importlib.util
import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

HAS_BPY = importlib.util.find_spec("bpy") is not None

requires_bpy = pytest.mark.skipif(not HAS_BPY, reason="module bpy absent")


def pytest_configure(config):
    config.addinivalue_line("markers", "bpy: nécessite le module bpy")


@pytest.fixture(scope="session")
def engine():
    """Un seul processus Blender pour toute la session de tests."""
    if not HAS_BPY:
        pytest.skip("module bpy absent")
    from blender_buildings.client import BlenderEngine

    with BlenderEngine(backend="module") as e:
        yield e


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    d = tmp_path / "output"
    d.mkdir()
    monkeypatch.setenv("BLENDER_BUILDINGS_OUTPUT", str(d))
    return d
