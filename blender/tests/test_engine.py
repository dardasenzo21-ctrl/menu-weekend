"""Le moteur en sous-processus (protocole JSON) et son client."""

import os

import pytest

from conftest import requires_bpy

from blender_buildings.client import BlenderEngine, EngineCrashed, EngineError, find_blender_binary

pytestmark = requires_bpy


def test_ping_and_info(engine):
    info = engine.ping()
    assert info["pong"] and info["background"]
    assert engine.alive and engine.resolved_backend == "module"


def test_build_render_export(engine, tmp_path):
    r = engine.build_building(preset="office", overrides={"floors": 3}, reset=True)
    assert r["metrics"]["floors"] == 3
    png = engine.render(str(tmp_path / "o.png"), engine="workbench", width=120, height=80)
    assert os.path.getsize(png["path"]) > 500
    glb = engine.export(str(tmp_path / "o.glb"))
    assert glb["size_bytes"] > 1000


def test_errors_are_propagated(engine):
    with pytest.raises(EngineError) as exc:
        engine.call("build_building", preset="nope")
    assert "Preset inconnu" in str(exc.value)
    assert exc.value.traceback_text
    with pytest.raises(EngineError):
        engine.call("does_not_exist")
    assert engine.alive  # une erreur ne tue pas le moteur


def test_run_python(engine):
    r = engine.call("run_python", code="import bpy\nprint('x')\nresult = {'n': len(bpy.data.objects)}")
    assert r["stdout"] == "x\n" and "n" in r["result"]


def test_stdout_noise_does_not_break_protocol(engine):
    # Blender écrit sur stdout pendant les rendus/exports ; le canal JSON doit rester propre.
    for _ in range(3):
        engine.call("run_python", code="print('bruit ' * 50)")
        assert engine.call("ping")["pong"]


def test_crash_recovery(tmp_path):
    with BlenderEngine(backend="module") as e:
        with pytest.raises(EngineCrashed):
            e.call("run_python", code="import os; os._exit(3)")
        assert not e.alive
        # redémarrage automatique au prochain appel
        assert e.ping()["pong"]


def test_timeout(tmp_path):
    with BlenderEngine(backend="module", timeout=2) as e:
        with pytest.raises(EngineCrashed):
            e.call("run_python", code="import time; time.sleep(10)")


def test_binary_backend_if_available(tmp_path):
    binary = find_blender_binary()
    if not binary:
        pytest.skip("binaire Blender introuvable")
    with BlenderEngine(backend="binary") as e:
        assert e.resolved_backend == "binary"
        r = e.build_building(preset="house", reset=True)
        assert r["faces"] > 100


def test_unknown_backend():
    with pytest.raises(EngineError):
        BlenderEngine(backend="weird").start()
