"""API HTTP (FastAPI) : la même puissance que le serveur MCP, pour n'importe quel client.

Lancement : ``blender-buildings-api --port 8080`` puis ``http://127.0.0.1:8080/docs`` (Swagger).
"""

from __future__ import annotations

import argparse
import os
import re
import time
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import __version__
from .client import BlenderEngine, EngineError, shared_engine
from .metrics import compute_metrics, format_metrics
from .presets import get_preset, list_presets
from .spec import BlockSpec, BuildingSpec, StreetSpec, spec_json_schema


def _output_dir() -> str:
    d = os.environ.get("BLENDER_BUILDINGS_OUTPUT") or os.path.join(os.getcwd(), "output")
    os.makedirs(d, exist_ok=True)
    return d


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "model"


class BuildRequest(BaseModel):
    preset: str | None = None
    spec: dict[str, Any] | None = None
    overrides: dict[str, Any] | None = None
    reset: bool = True


class StreetRequest(StreetSpec):
    reset: bool = True


class BlockRequest(BaseModel):
    name: str = "Block"
    buildings: list[BuildRequest] = Field(min_length=1)
    ground_size: float = 200.0
    reset: bool = True


class RenderRequest(BaseModel):
    view: Literal["perspective", "iso", "front", "back", "left", "right", "top"] = "perspective"
    engine: Literal["workbench", "eevee", "cycles"] = "eevee"
    width: int = Field(1280, ge=64, le=8192)
    height: int = Field(720, ge=64, le=8192)
    samples: int = Field(16, ge=1, le=4096)
    azimuth: float = 35.0
    elevation: float = 22.0
    name: str = "render"


class ExportRequest(BaseModel):
    format: Literal["glb", "gltf", "fbx", "obj", "stl", "usd", "usdc", "usda", "ply", "blend"] = "glb"
    name: str = "model"
    objects: list[str] | None = None
    include_ground: bool = False


class PythonRequest(BaseModel):
    code: str


def _resolve(req: BuildRequest) -> BuildingSpec:
    try:
        if req.spec is not None:
            base = get_preset(req.preset).with_overrides(req.spec) if req.preset else BuildingSpec.model_validate(req.spec)
            return base.with_overrides(req.overrides)
        if req.preset:
            return get_preset(req.preset, req.overrides)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail="Fournir `preset` ou `spec`.")


def create_app(engine: BlenderEngine | None = None) -> FastAPI:
    app = FastAPI(title="blender-buildings API", version=__version__, description="Modélisation paramétrique de bâtiments dans Blender (headless).")
    get_engine = (lambda: engine) if engine is not None else (lambda: shared_engine(backend=os.environ.get("BLENDER_BACKEND", "auto"), blender_bin=os.environ.get("BLENDER_BIN")))

    @app.exception_handler(EngineError)
    async def _engine_error(_: Any, exc: EngineError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc), "traceback": exc.traceback_text})

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @app.get("/engine")
    def engine_status() -> dict[str, Any]:
        e = get_engine()
        return {"alive": e.alive, "backend": getattr(e, "resolved_backend", e.backend), "info": e.ping(), "output_dir": _output_dir()}

    @app.get("/presets")
    def presets() -> dict[str, Any]:
        return {"presets": list_presets()}

    @app.get("/presets/{name}")
    def preset(name: str) -> dict[str, Any]:
        try:
            return get_preset(name).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/schema")
    def schema() -> dict[str, Any]:
        return spec_json_schema()

    @app.get("/materials")
    def materials() -> dict[str, Any]:
        return get_engine().call("list_materials")

    @app.post("/metrics")
    def metrics(req: BuildRequest) -> dict[str, Any]:
        m = compute_metrics(_resolve(req))
        return {"metrics": m, "summary": format_metrics(m)}

    @app.post("/build")
    def build(req: BuildRequest) -> dict[str, Any]:
        s = _resolve(req)
        r = get_engine().call("build_building", spec=s.model_dump(mode="json"), reset=req.reset)
        r["summary"] = format_metrics(r["metrics"])
        return r

    @app.post("/street")
    def street(req: StreetRequest) -> dict[str, Any]:
        data = req.model_dump(mode="json")
        reset = data.pop("reset")
        return get_engine().call("build_street", street=data, reset=reset)

    @app.post("/block")
    def block(req: BlockRequest) -> dict[str, Any]:
        specs = [_resolve(b) for b in req.buildings]
        blk = BlockSpec(name=req.name, buildings=specs, site={"ground": True, "ground_size": req.ground_size})
        return get_engine().call("build_block", block=blk.model_dump(mode="json"), reset=req.reset)

    @app.post("/render")
    def render(req: RenderRequest) -> dict[str, Any]:
        path = os.path.join(_output_dir(), f"{_slug(req.name)}_{req.view}_{int(time.time())}.png")
        r = get_engine().call("render", path=path, view=req.view, engine=req.engine, width=req.width, height=req.height, samples=req.samples, azimuth=req.azimuth, elevation=req.elevation)
        r["url"] = f"/files/{os.path.basename(path)}"
        return r

    @app.post("/export")
    def export(req: ExportRequest) -> dict[str, Any]:
        path = os.path.join(_output_dir(), f"{_slug(req.name)}_{int(time.time())}.{req.format}")
        r = get_engine().call("export", path=path, format=req.format, objects=req.objects, include_ground=req.include_ground)
        r["url"] = f"/files/{os.path.basename(path)}"
        return r

    @app.post("/save")
    def save(name: str = "scene") -> dict[str, Any]:
        path = os.path.join(_output_dir(), f"{_slug(name)}_{int(time.time())}.blend")
        r = get_engine().call("save", path=path)
        r["url"] = f"/files/{os.path.basename(path)}"
        return r

    @app.get("/scene")
    def scene() -> dict[str, Any]:
        return get_engine().call("scene_info")

    @app.post("/reset")
    def reset() -> dict[str, Any]:
        return get_engine().call("reset")

    @app.delete("/objects")
    def delete_objects(names: list[str]) -> dict[str, Any]:
        return get_engine().call("delete", objects=names)

    @app.post("/python")
    def run_python(req: PythonRequest) -> dict[str, Any]:
        if os.environ.get("BLENDER_BUILDINGS_ALLOW_PYTHON", "1") in ("0", "false", "no"):
            raise HTTPException(status_code=403, detail="run_python désactivé")
        return get_engine().call("run_python", code=req.code)

    @app.get("/files")
    def files() -> dict[str, Any]:
        d = _output_dir()
        items = sorted(os.listdir(d), key=lambda n: os.path.getmtime(os.path.join(d, n)), reverse=True)
        return {"files": [{"name": n, "size_bytes": os.path.getsize(os.path.join(d, n)), "url": f"/files/{n}"} for n in items]}

    @app.get("/files/{name}")
    def file(name: str) -> FileResponse:
        safe = os.path.basename(name)
        path = os.path.join(_output_dir(), safe)
        if safe != name or not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Fichier introuvable")
        return FileResponse(path)

    return app


app = create_app()


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    parser = argparse.ArgumentParser(prog="blender-buildings-api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--backend", choices=["auto", "module", "binary"], default=None)
    parser.add_argument("--blender", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    if args.backend:
        os.environ["BLENDER_BACKEND"] = args.backend
    if args.blender:
        os.environ["BLENDER_BIN"] = args.blender
    if args.output:
        os.environ["BLENDER_BUILDINGS_OUTPUT"] = os.path.abspath(args.output)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
