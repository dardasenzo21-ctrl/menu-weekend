import json

import pytest

from conftest import HAS_BPY

from blender_buildings.cli import main


def test_presets_and_metrics(capsys):
    main(["presets"])
    assert "haussmann" in capsys.readouterr().out
    main(["metrics", "--preset", "office", "--set", "floors=3", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["floors"] == 3


def test_show_with_spec_file(tmp_path, capsys):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"name": "X", "floors": 2}), encoding="utf-8")
    main(["show", "--spec", str(p), "--set", "roof.kind=hip"])
    out = json.loads(capsys.readouterr().out)
    assert out["name"] == "X" and out["roof"]["kind"] == "hip"


def test_bad_set():
    with pytest.raises(SystemExit):
        main(["metrics", "--preset", "office", "--set", "floors"])
    with pytest.raises(SystemExit):
        main(["metrics"])


@pytest.mark.skipif(not HAS_BPY, reason="module bpy absent")
def test_build_command(tmp_path, capsys):
    main(["build", "--preset", "house", "--backend", "module", "--out", str(tmp_path), "--formats", "glb,png", "--views", "front", "--render-engine", "workbench", "--width", "120", "--height", "80"])
    out = capsys.readouterr().out
    assert "rendu :" in out and "export :" in out
    assert (tmp_path / "Maison_individuelle.glb").exists()
    assert (tmp_path / "Maison_individuelle_front.png").exists()
