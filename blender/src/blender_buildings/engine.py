"""Moteur Blender : processus qui exécute des commandes JSON (une par ligne) dans ``bpy``.

Protocole (stdin → engine) : ``{"id": 1, "op": "build_building", "args": {...}}``
Réponse (engine → fd dédié) : ``{"id": 1, "ok": true, "result": {...}}`` ou ``{"id": 1, "ok": false, "error": "...", "traceback": "..."}``

Le flux stdout de Blender (progression de rendu, logs d'export) est redirigé vers stderr
pour ne jamais polluer le canal de réponses.

Lancement :

* avec le module pip ``bpy`` : ``python -m blender_buildings.engine``
* avec le binaire Blender : ``blender -b --python engine.py -- --site <site-packages du venv>``
"""

from __future__ import annotations

import io
import json
import os
import sys
import traceback
from typing import Any, Callable


def _bootstrap_paths() -> None:
    """Sous le binaire Blender : ajoute ``src`` et les ``--site`` passés après ``--``."""
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.dirname(here)
    if src not in sys.path:
        sys.path.insert(0, src)
    argv = sys.argv
    if "--" in argv:
        extra = argv[argv.index("--") + 1 :]
        i = 0
        while i < len(extra):
            if extra[i] == "--site" and i + 1 < len(extra):
                if extra[i + 1] not in sys.path:
                    sys.path.append(extra[i + 1])
                i += 2
            else:
                i += 1


_bootstrap_paths()

import bpy  # noqa: E402

from blender_buildings import __version__  # noqa: E402
from blender_buildings import exporters, scene  # noqa: E402
from blender_buildings.builder import build_block, build_building, build_street, generate_street  # noqa: E402
from blender_buildings.materials import list_materials  # noqa: E402
from blender_buildings.metrics import compute_metrics  # noqa: E402
from blender_buildings.presets import get_preset, list_presets  # noqa: E402
from blender_buildings.spec import BuildingSpec, spec_json_schema  # noqa: E402

ALLOW_PYTHON = os.environ.get("BLENDER_BUILDINGS_ALLOW_PYTHON", "1") not in ("0", "false", "no")


def _resolve_spec(spec: dict[str, Any] | None = None, preset: str | None = None, overrides: dict[str, Any] | None = None) -> BuildingSpec:
    if spec is not None:
        return BuildingSpec.model_validate(spec).with_overrides(overrides)
    if preset:
        return get_preset(preset, overrides)
    raise ValueError("Fournir 'spec' ou 'preset'")


# ----------------------------------------------------------------------------------------------
# Opérations exposées
# ----------------------------------------------------------------------------------------------
def op_ping() -> dict[str, Any]:
    return {"pong": True, "blender": bpy.app.version_string, "background": bpy.app.background, "version": __version__, "python": sys.version.split()[0], "allow_python": ALLOW_PYTHON}


def op_reset() -> dict[str, Any]:
    scene.reset_scene()
    return {"reset": True}


def op_build_building(spec: dict[str, Any] | None = None, preset: str | None = None, overrides: dict[str, Any] | None = None, reset: bool = False) -> dict[str, Any]:
    if reset:
        scene.reset_scene()
    s = _resolve_spec(spec, preset, overrides)
    return build_building(s)


def op_build_block(block: dict[str, Any], reset: bool = False) -> dict[str, Any]:
    if reset:
        scene.reset_scene()
    return build_block(block)


def op_build_street(street: dict[str, Any], reset: bool = False) -> dict[str, Any]:
    if reset:
        scene.reset_scene()
    return build_street(street)


def op_generate_street(street: dict[str, Any]) -> dict[str, Any]:
    return generate_street(street).model_dump(mode="json")


def op_metrics(spec: dict[str, Any] | None = None, preset: str | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    return compute_metrics(_resolve_spec(spec, preset, overrides))


def op_render(path: str, view: str = "perspective", engine: str = "eevee", width: int = 1280, height: int = 720, samples: int = 16, objects: list[str] | None = None, azimuth: float = 35.0, elevation: float = 22.0) -> dict[str, Any]:
    return scene.render_image(path, view=view, engine=engine, resolution=(int(width), int(height)), samples=int(samples), names=objects, azimuth=azimuth, elevation=elevation)  # type: ignore[arg-type]


def op_export(path: str, format: str | None = None, objects: list[str] | None = None, include_ground: bool = False) -> dict[str, Any]:
    return exporters.export_scene(path, format, objects, include_ground)


def op_save(path: str) -> dict[str, Any]:
    return exporters.save_blend(path)


def op_open(path: str) -> dict[str, Any]:
    return exporters.open_blend(path)


def op_scene_info() -> dict[str, Any]:
    return scene.scene_info()


def op_delete(objects: list[str]) -> dict[str, Any]:
    return {"removed": scene.delete_objects(objects)}


def op_list_presets() -> dict[str, Any]:
    return {"presets": list_presets()}


def op_get_preset(name: str) -> dict[str, Any]:
    return get_preset(name).model_dump(mode="json")


def op_list_materials() -> dict[str, Any]:
    return {"materials": list_materials()}


def op_spec_schema() -> dict[str, Any]:
    return spec_json_schema()


def op_run_python(code: str) -> dict[str, Any]:
    """Exécute du Python arbitraire dans Blender (désactivable : BLENDER_BUILDINGS_ALLOW_PYTHON=0)."""
    if not ALLOW_PYTHON:
        raise PermissionError("run_python désactivé (BLENDER_BUILDINGS_ALLOW_PYTHON=0)")
    buf = io.StringIO()
    old = sys.stdout
    ns: dict[str, Any] = {"bpy": bpy, "__name__": "__bb_user__"}
    sys.stdout = buf
    try:
        exec(compile(code, "<run_python>", "exec"), ns)
    finally:
        sys.stdout = old
    result = ns.get("result")
    try:
        json.dumps(result)
    except TypeError:
        result = repr(result)
    return {"stdout": buf.getvalue(), "result": result}


OPS: dict[str, Callable[..., dict[str, Any]]] = {
    "ping": op_ping,
    "reset": op_reset,
    "build_building": op_build_building,
    "build_block": op_build_block,
    "build_street": op_build_street,
    "generate_street": op_generate_street,
    "metrics": op_metrics,
    "render": op_render,
    "export": op_export,
    "save": op_save,
    "open": op_open,
    "scene_info": op_scene_info,
    "delete": op_delete,
    "list_presets": op_list_presets,
    "get_preset": op_get_preset,
    "list_materials": op_list_materials,
    "spec_schema": op_spec_schema,
    "run_python": op_run_python,
}


def handle(message: dict[str, Any]) -> dict[str, Any]:
    mid = message.get("id")
    op = message.get("op")
    args = message.get("args") or {}
    fn = OPS.get(op or "")
    if fn is None:
        return {"id": mid, "ok": False, "error": f"Opération inconnue : {op!r}", "ops": sorted(OPS)}
    try:
        return {"id": mid, "ok": True, "result": fn(**args)}
    except Exception as exc:  # noqa: BLE001 — on renvoie tout au client
        return {"id": mid, "ok": False, "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}


def serve() -> None:
    # Canal de réponses = copie du stdout original ; tout le reste part sur stderr.
    resp_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    def send(obj: dict[str, Any]) -> None:
        data = (json.dumps(obj, ensure_ascii=False, default=str) + "\n").encode("utf-8")
        view = memoryview(data)
        while view:
            n = os.write(resp_fd, view)
            view = view[n:]

    send({"id": None, "ok": True, "result": op_ping(), "event": "ready"})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            send({"id": None, "ok": False, "error": f"JSON invalide : {exc}"})
            continue
        if message.get("op") == "quit":
            send({"id": message.get("id"), "ok": True, "result": {"bye": True}})
            break
        send(handle(message))


if __name__ == "__main__":
    serve()
