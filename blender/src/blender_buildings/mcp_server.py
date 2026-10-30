"""Serveur MCP (Model Context Protocol) « blender-buildings ».

Expose la modélisation paramétrique de bâtiments à Claude Code, Claude Desktop, Cursor, etc.

Lancement :

* ``blender-buildings-mcp`` (stdio, défaut) ;
* ``blender-buildings-mcp --http --port 8765`` (Streamable HTTP sur ``/mcp``).

Variables d'environnement :

* ``BLENDER_BACKEND`` = ``auto`` | ``module`` | ``binary`` ;
* ``BLENDER_BIN`` = chemin de l'exécutable Blender (backend ``binary``) ;
* ``BLENDER_BUILDINGS_OUTPUT`` = dossier de sortie des rendus/exports (défaut : ``./output``) ;
* ``BLENDER_BUILDINGS_ALLOW_PYTHON`` = ``0`` pour désactiver l'outil ``run_blender_python``.
"""

from __future__ import annotations

import argparse
import functools
import os
import re
import time
from typing import Any, Callable, Literal

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__
from .client import BlenderEngine, shared_engine
from .metrics import compute_metrics, format_metrics
from .presets import PRESETS, get_preset, list_presets
from .spec import BuildingSpec, StreetSpec, spec_json_schema

INSTRUCTIONS = """Serveur de modélisation 3D de bâtiments dans Blender (headless).

Flux typique :
1. `list_presets` pour voir les typologies (haussmann, bureaux, hôtel, logistique, maison…).
2. `build_building` avec un preset et des `overrides` (ex. {"floors": 8, "roof.kind": "hip"}) ou une `spec` complète (`get_spec_schema`).
3. `render_preview` pour voir le résultat (perspective, élévations front/left/top…).
4. `export_model` en GLB/FBX/OBJ/USD pour le réutiliser (Three.js, Unity, Twinmotion, Revit…).
5. `compute_metrics` donne emprise, surface de plancher, surface utile, vitrage, nombre de logements, CES, valorisation.
6. `build_from_address("8 rue Pasquier 75008 Paris")` modélise un bâtiment RÉEL (emprise cadastrale, hauteur IGN, voisins, orthophoto).

Toutes les dimensions sont en mètres. La scène Blender persiste entre les appels : `reset_scene` pour repartir de zéro.
"""


def _output_dir() -> str:
    d = os.environ.get("BLENDER_BUILDINGS_OUTPUT") or os.path.join(os.getcwd(), "output")
    os.makedirs(d, exist_ok=True)
    return d


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "model"


def _out_path(name: str, ext: str) -> str:
    return os.path.join(_output_dir(), f"{_slug(name)}_{int(time.time())}.{ext}")


def _engine() -> BlenderEngine:
    return shared_engine(backend=os.environ.get("BLENDER_BACKEND", "auto"), blender_bin=os.environ.get("BLENDER_BIN"))


def create_server(engine: BlenderEngine | None = None) -> MCPServer:
    server = MCPServer("blender-buildings", version=__version__, instructions=INSTRUCTIONS)
    get_engine = (lambda: engine) if engine is not None else _engine

    # ---- découverte ----------------------------------------------------------------------------
    @_tool(server, description="Liste les presets de bâtiments disponibles (id, nom, usage, description).")
    def list_building_presets() -> dict[str, Any]:
        return {"presets": list_presets()}

    @_tool(server, description="Retourne la spécification complète (JSON) d'un preset, à modifier puis passer à build_building.")
    def get_preset_spec(preset: str) -> dict[str, Any]:
        return get_preset(preset).model_dump(mode="json")

    @_tool(server, description="Schéma JSON d'une BuildingSpec : tous les champs paramétrables (emprise, étages, fenêtres, toiture, balcons, façade, matériaux).")
    def get_spec_schema() -> dict[str, Any]:
        return spec_json_schema()

    @_tool(server, description="Liste les matériaux disponibles (pierre, enduit, béton, brique, verre, zinc, bois, corten…).")
    def list_materials() -> dict[str, Any]:
        return get_engine().call("list_materials")

    # ---- métriques (sans Blender) --------------------------------------------------------------
    @_tool(server, description="Calcule les métriques immobilières d'un bâtiment SANS le construire : emprise, surface de plancher, surface utile, façades, vitrage, logements/postes, CES et valorisation (si price_per_m2). Fournir `preset` et/ou `spec`, plus `overrides` (clés pointées : 'roof.kind').")
    def compute_building_metrics(preset: str | None = None, spec: dict[str, Any] | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        s = _resolve(preset, spec, overrides)
        m = compute_metrics(s)
        return {"metrics": m, "summary": format_metrics(m)}

    # ---- construction --------------------------------------------------------------------------
    @_tool(server, description="Construit un bâtiment paramétrique dans la scène Blender. `preset` (ex. 'haussmann') et/ou `spec` complète, `overrides` pour ajuster (ex. {'floors': 7, 'footprint.width': 25, 'roof.kind': 'mansard', 'facade.material': 'brick_red'}). `reset=true` vide la scène avant. Retourne l'objet créé, ses stats et ses métriques.")
    def build_building(preset: str | None = None, spec: dict[str, Any] | None = None, overrides: dict[str, Any] | None = None, reset: bool = True, name: str | None = None, position: list[float] | None = None, rotation_deg: float | None = None) -> dict[str, Any]:
        s = _resolve(preset, spec, overrides)
        extra: dict[str, Any] = {}
        if name:
            extra["name"] = name
        if position:
            extra["position"] = tuple(position)
        if rotation_deg is not None:
            extra["rotation_deg"] = rotation_deg
        s = s.with_overrides(extra)
        result = get_engine().call("build_building", spec=s.model_dump(mode="json"), reset=reset)
        result["summary"] = format_metrics(result["metrics"])
        return result

    @_tool(server, description="Génère une rue / un îlot : N bâtiments alignés d'un preset, variés aléatoirement (largeur, étages) par `seed`. `overrides` s'applique à tous.")
    def build_street(preset: str = "haussmann", count: int = 5, seed: int = 1, gap: float = 0.0, floors_min: int = 5, floors_max: int = 7, width_min: float = 12.0, width_max: float = 24.0, overrides: dict[str, Any] | None = None, reset: bool = True, name: str = "Street") -> dict[str, Any]:
        street = StreetSpec(name=name, preset=preset, count=count, seed=seed, gap=gap, floors_range=(floors_min, floors_max), width_range=(width_min, width_max), overrides=overrides or {})
        return get_engine().call("build_street", street=street.model_dump(mode="json"), reset=reset)

    @_tool(server, description="Construit plusieurs bâtiments définis explicitement (liste de specs avec `position`/`rotation_deg`).")
    def build_block(buildings: list[dict[str, Any]], name: str = "Block", reset: bool = True, ground_size: float = 200.0) -> dict[str, Any]:
        specs = [_resolve(b.get("preset"), b.get("spec") or (None if "preset" in b else b), b.get("overrides")).model_dump(mode="json") for b in buildings]
        block = {"name": name, "buildings": specs, "site": {"ground": True, "ground_size": ground_size}}
        return get_engine().call("build_block", block=block, reset=reset)

    @_tool(server, description="Modélise un SITE RÉEL à partir d'une adresse française : géocodage, emprise cadastrale exacte et hauteur/étages IGN BD TOPO du bâtiment, parcelle, tags OpenStreetMap, bâtiments voisins en volumétrie (vraies hauteurs) et orthophoto IGN plaquée au sol. Puis `render_preview(view='street', azimuth=<facade_azimuth_deg>)` pour la vue piéton, `view='perspective'` pour l'îlot. `overrides` ajuste le bâtiment cible (ex. {'roof.kind': 'mansard', 'facade.material': 'brick_red'}).")
    def build_from_address(address: str, radius_m: float = 80.0, context: bool = True, orthophoto: bool = True, overrides: dict[str, Any] | None = None, reset: bool = True) -> dict[str, Any]:
        from .geo import site_from_address

        site = site_from_address(address, radius_m=radius_m, context=context, orthophoto=orthophoto, ortho_dir=_output_dir(), overrides=overrides)
        result = get_engine().call("build_site", site=site.model_dump(mode="json"), reset=reset, context=context, ground=True)
        result["target"]["summary"] = format_metrics(result["target"]["metrics"])
        result["target_spec"] = site.target.model_dump(mode="json")
        result["hint"] = f"Vue piéton : render_preview(view='street', azimuth={site.facade_azimuth_deg}, street_distance={max(10.0, site.street_distance_m)})"
        return result

    @_tool(server, description="Récupère les données d'un site réel (adresse française) SANS construire : spec du bâtiment cible (emprise, hauteur, étages IGN), parcelle, voisins, sources. Utile pour inspecter/ajuster avant build_building(spec=...).")
    def fetch_site_data(address: str, radius_m: float = 80.0) -> dict[str, Any]:
        from .geo import site_from_address

        site = site_from_address(address, radius_m=radius_m, context=True, orthophoto=False, osm=True)
        return {"label": site.label, "lat": site.lat, "lon": site.lon, "target": site.target.model_dump(mode="json"), "metrics": compute_metrics(site.target), "parcel": {k: v for k, v in (site.parcel or {}).items() if k != "ring"}, "context_count": len(site.context), "facade_azimuth_deg": site.facade_azimuth_deg, "sources": site.sources, "notes": site.notes}

    # ---- sortie --------------------------------------------------------------------------------
    @_tool(server, structured_output=False, description="Rend une image PNG de la scène et la retourne. `view` : perspective, iso, street (piéton face à la façade orientée vers `azimuth`, à `street_distance` m), front, back, left, right, top (élévations orthographiques). `objects` limite le cadrage à ces objets, `solo` masque les autres bâtiments. `engine` : workbench (instantané, aplats), eevee (réaliste, ~10-30 s), cycles (lent). Retourne aussi le chemin du fichier.")
    def render_preview(view: Literal["perspective", "iso", "street", "front", "back", "left", "right", "top"] = "perspective", engine: Literal["workbench", "eevee", "cycles"] = "eevee", width: int = 1280, height: int = 720, samples: int = 16, azimuth: float = 35.0, elevation: float = 22.0, objects: list[str] | None = None, solo: bool = False, street_distance: float = 12.0, path: str | None = None) -> list[Image | str]:
        path = path or _out_path(f"render_{view}", "png")
        result = get_engine().call("render", path=path, view=view, engine=engine, width=width, height=height, samples=samples, azimuth=azimuth, elevation=elevation, objects=objects, solo=solo, street_distance=street_distance)
        return [Image(path=path), f"Rendu {view} ({result['engine']}) enregistré : {path}"]

    @_tool(server, description="Exporte les bâtiments de la scène : glb, gltf, fbx, obj, stl, usd, usdc, usda, ply ou blend. Retourne le chemin et la taille du fichier.")
    def export_model(format: Literal["glb", "gltf", "fbx", "obj", "stl", "usd", "usdc", "usda", "ply", "blend"] = "glb", path: str | None = None, objects: list[str] | None = None, include_ground: bool = False) -> dict[str, Any]:
        path = path or _out_path("model", format)
        return get_engine().call("export", path=path, format=format, objects=objects, include_ground=include_ground)

    @_tool(server, description="Sauvegarde la scène courante en fichier .blend (ouvrable dans Blender).")
    def save_blend(path: str | None = None) -> dict[str, Any]:
        return get_engine().call("save", path=path or _out_path("scene", "blend"))

    @_tool(server, description="Ouvre un fichier .blend existant dans le moteur.")
    def open_blend(path: str) -> dict[str, Any]:
        return get_engine().call("open", path=path)

    # ---- scène ---------------------------------------------------------------------------------
    @_tool(server, description="Décrit la scène Blender courante : objets, nombre de faces, matériaux, emprise globale.")
    def scene_info() -> dict[str, Any]:
        return get_engine().call("scene_info")

    @_tool(server, description="Vide la scène Blender.")
    def reset_scene() -> dict[str, Any]:
        return get_engine().call("reset")

    @_tool(server, description="Supprime des objets de la scène par nom.")
    def delete_objects(objects: list[str]) -> dict[str, Any]:
        return get_engine().call("delete", objects=objects)

    if os.environ.get("BLENDER_BUILDINGS_ALLOW_PYTHON", "1") not in ("0", "false", "no"):

        @_tool(server, description="Exécute du code Python (bpy) dans le moteur Blender pour tout ce que les outils paramétriques ne couvrent pas. Affecter `result` pour retourner une valeur JSON ; stdout est capturé.")
        def run_blender_python(code: str) -> dict[str, Any]:
            return get_engine().call("run_python", code=code)

    @_tool(server, description="État du moteur Blender (version, backend, processus vivant) et derniers logs.")
    def engine_status() -> dict[str, Any]:
        e = get_engine()
        info = e.ping()
        return {"alive": e.alive, "backend": getattr(e, "resolved_backend", e.backend), "info": info, "output_dir": _output_dir(), "log_tail": e.log.splitlines()[-20:]}

    # ---- ressources & prompts ------------------------------------------------------------------
    @server.resource("presets://list", description="Presets de bâtiments disponibles", mime_type="application/json")
    def presets_resource() -> str:
        import json

        return json.dumps(list_presets(), ensure_ascii=False, indent=2)

    @server.resource("presets://{name}", description="Spécification JSON d'un preset", mime_type="application/json")
    def preset_resource(name: str) -> str:
        import json

        return json.dumps(PRESETS[name], ensure_ascii=False, indent=2)

    @server.resource("spec://schema", description="Schéma JSON d'une BuildingSpec", mime_type="application/json")
    def schema_resource() -> str:
        import json

        return json.dumps(spec_json_schema(), ensure_ascii=False)

    @server.prompt(description="Conçoit un bâtiment à partir d'un brief immobilier (programme, parcelle, contraintes).")
    def design_building(brief: str) -> str:
        return (
            "Tu es architecte-programmiste. À partir du brief ci-dessous, choisis un preset avec `list_building_presets`, "
            "ajuste-le avec `build_building` (overrides) pour respecter le programme, vérifie `compute_building_metrics` "
            "(surface de plancher, logements, CES si parcelle donnée), rends une perspective et une élévation avec `render_preview`, "
            "puis exporte en GLB avec `export_model`. Explique tes choix (gabarit, toiture, matériaux) en français.\n\n"
            f"Brief : {brief}"
        )

    return server


def _tool(server: MCPServer, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Enregistre un outil en convertissant toute exception en ToolError lisible (message conservé)."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kw: Any) -> Any:
            try:
                return fn(*args, **kw)
            except ToolError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ToolError(f"{type(exc).__name__}: {exc}") from exc

        return server.tool(**kwargs)(wrapper)

    return decorator


def _resolve(preset: str | None, spec: dict[str, Any] | None, overrides: dict[str, Any] | None) -> BuildingSpec:
    if spec is not None:
        base = BuildingSpec.model_validate(spec)
        if preset:
            base = get_preset(preset).with_overrides(spec)
        return base.with_overrides(overrides)
    if preset:
        return get_preset(preset, overrides)
    raise ValueError("Fournir `preset` ou `spec`.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="blender-buildings-mcp", description="Serveur MCP de modélisation de bâtiments (Blender headless)")
    parser.add_argument("--http", action="store_true", help="Transport Streamable HTTP au lieu de stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--backend", choices=["auto", "module", "binary"], default=None, help="Force le backend Blender")
    parser.add_argument("--blender", default=None, help="Chemin de l'exécutable Blender (backend binary)")
    parser.add_argument("--output", default=None, help="Dossier de sortie des rendus/exports")
    parser.add_argument("--no-python", action="store_true", help="Désactive l'outil run_blender_python")
    args = parser.parse_args(argv)
    if args.backend:
        os.environ["BLENDER_BACKEND"] = args.backend
    if args.blender:
        os.environ["BLENDER_BIN"] = args.blender
    if args.output:
        os.environ["BLENDER_BUILDINGS_OUTPUT"] = os.path.abspath(args.output)
    if args.no_python:
        os.environ["BLENDER_BUILDINGS_ALLOW_PYTHON"] = "0"
    server = create_server()
    if args.http:
        server.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
