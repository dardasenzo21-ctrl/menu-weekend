"""CLI : ``blender-buildings <commande>``.

Exemples ::

    blender-buildings presets
    blender-buildings metrics --preset haussmann --set floors=8 --set site.parcel_area=600
    blender-buildings build --preset office --set floors=12 --out output/office --formats glb,fbx,png
    blender-buildings build --spec examples/haussmann_paris.json --out output/paris --views perspective,front
    blender-buildings street --preset haussmann --count 6 --out output/rue
    blender-buildings site --address "8 rue Pasquier 75008 Paris" --out output/pasquier   # site réel
    blender-buildings mcp            # serveur MCP (stdio)
    blender-buildings api --port 8080
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from . import __version__
from .metrics import compute_metrics, format_metrics
from .presets import get_preset, list_presets
from .spec import BuildingSpec, StreetSpec


def _parse_set(items: list[str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"--set attend clé=valeur, reçu : {item}")
        k, v = item.split("=", 1)
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def _load_spec(args: argparse.Namespace) -> BuildingSpec:
    overrides = _parse_set(getattr(args, "set", None))
    if getattr(args, "spec", None):
        with open(args.spec, encoding="utf-8") as fh:
            data = json.load(fh)
        spec = BuildingSpec.model_validate(data)
        if getattr(args, "preset", None):
            spec = get_preset(args.preset).with_overrides(data)
        return spec.with_overrides(overrides)
    if getattr(args, "preset", None):
        return get_preset(args.preset, overrides)
    raise SystemExit("Indiquer --preset ou --spec")


def cmd_presets(args: argparse.Namespace) -> None:
    for p in list_presets():
        print(f"{p['id']:<20} {p['use']:<12} {p['name']} — {p['description']}")


def cmd_show(args: argparse.Namespace) -> None:
    print(_load_spec(args).model_dump_json(indent=2))


def cmd_metrics(args: argparse.Namespace) -> None:
    m = compute_metrics(_load_spec(args))
    if args.json:
        print(json.dumps(m, ensure_ascii=False, indent=2))
    else:
        print(format_metrics(m))


def _engine(args: argparse.Namespace):
    from .client import BlenderEngine

    return BlenderEngine(backend=args.backend, blender_bin=args.blender)


def _outputs(engine: Any, out: str, base: str, formats: list[str], views: list[str], render_engine: str, size: tuple[int, int]) -> None:
    os.makedirs(out, exist_ok=True)
    for fmt in formats:
        if fmt == "png":
            for view in views:
                r = engine.call("render", path=os.path.join(out, f"{base}_{view}.png"), view=view, engine=render_engine, width=size[0], height=size[1])
                print("rendu :", r["path"])
        else:
            r = engine.call("export", path=os.path.join(out, f"{base}.{fmt}"), format=fmt)
            print("export :", r["path"], f"({r['size_bytes']} octets)")


def cmd_build(args: argparse.Namespace) -> None:
    spec = _load_spec(args)
    with _engine(args) as engine:
        r = engine.call("build_building", spec=spec.model_dump(mode="json"), reset=True)
        print(f"{r['object']} : {r['faces']} faces, {r['vertices']} sommets, {r['height_m']} m")
        print(format_metrics(r["metrics"]))
        _outputs(engine, args.out, spec.name.replace(" ", "_"), args.formats.split(","), args.views.split(","), args.render_engine, (args.width, args.height))


def cmd_street(args: argparse.Namespace) -> None:
    street = StreetSpec(preset=args.preset, count=args.count, seed=args.seed, gap=args.gap, floors_range=(args.floors_min, args.floors_max), width_range=(args.width_min, args.width_max), overrides=_parse_set(args.set))
    with _engine(args) as engine:
        r = engine.call("build_street", street=street.model_dump(mode="json"), reset=True)
        print(f"{len(r['buildings'])} bâtiments, SDP totale {r['total_gross_floor_area_m2']} m²")
        _outputs(engine, args.out, "street", args.formats.split(","), args.views.split(","), args.render_engine, (args.width, args.height))


def cmd_site(args: argparse.Namespace) -> None:
    from .geo import site_from_address

    os.makedirs(args.out, exist_ok=True)
    site = site_from_address(args.address, radius_m=args.radius, context=not args.no_context, orthophoto=not args.no_ortho, ortho_dir=args.out, overrides=_parse_set(args.set))
    print(f"{site.label} ({site.lat:.6f}, {site.lon:.6f}) — {len(site.context)} voisins — sources : {', '.join(site.sources)}")
    for n in site.notes:
        print("note :", n)
    with open(os.path.join(args.out, "site.json"), "w", encoding="utf-8") as fh:
        fh.write(site.model_dump_json(indent=1))
    print(format_metrics(compute_metrics(site.target)))
    if args.no_build:
        return
    with _engine(args) as engine:
        r = engine.call("build_site", site=site.model_dump(mode="json"), reset=True)
        tgt = r["target"]["object"]
        base = "site"
        for fmt in args.formats.split(","):
            if fmt == "png":
                for view in args.views.split(","):
                    kw: dict[str, Any] = {"view": view, "engine": args.render_engine, "width": args.width, "height": args.height}
                    if view == "street":
                        kw.update(objects=[tgt], azimuth=site.facade_azimuth_deg, street_distance=max(10.0, site.street_distance_m), width=min(args.width, args.height), height=max(args.width, args.height))
                    elif view in ("front", "back", "left", "right"):
                        kw.update(objects=[tgt], solo=True)
                    r2 = engine.call("render", path=os.path.join(args.out, f"{base}_{view}.png"), **kw)
                    print("rendu :", r2["path"])
            else:
                r2 = engine.call("export", path=os.path.join(args.out, f"{base}.{fmt}"), format=fmt)
                print("export :", r2["path"], f"({r2['size_bytes']} octets)")
                r3 = engine.call("export", path=os.path.join(args.out, f"batiment.{fmt}"), format=fmt, objects=[tgt])
                print("export :", r3["path"], f"({r3['size_bytes']} octets)")


def cmd_mcp(args: argparse.Namespace) -> None:
    from .mcp_server import main as mcp_main

    mcp_main(args.rest)


def cmd_api(args: argparse.Namespace) -> None:
    from .api import main as api_main

    api_main(args.rest)


def cmd_doctor(args: argparse.Namespace) -> None:
    from .client import find_blender_binary, module_backend_available

    print(f"blender-buildings {__version__} — Python {sys.version.split()[0]}")
    print("module bpy :", "OK" if module_backend_available() else "absent (pip install bpy==5.2.3, Python 3.13)")
    print("binaire Blender :", find_blender_binary() or "introuvable (définir BLENDER_BIN)")
    try:
        with _engine(args) as e:
            print("moteur :", e.resolved_backend, e.info)
    except Exception as exc:
        print("moteur : ERREUR", exc)


def _add_engine_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--backend", choices=["auto", "module", "binary"], default=os.environ.get("BLENDER_BACKEND", "auto"))
    p.add_argument("--blender", default=os.environ.get("BLENDER_BIN"))


def _add_output_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", default="output")
    p.add_argument("--formats", default="glb,png", help="Liste séparée par des virgules : glb,gltf,fbx,obj,stl,usd,ply,blend,png")
    p.add_argument("--views", default="perspective", help="Vues PNG : perspective,iso,front,back,left,right,top")
    p.add_argument("--render-engine", default="eevee", choices=["workbench", "eevee", "cycles"])
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blender-buildings", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("presets", help="Liste les presets").set_defaults(fn=cmd_presets)

    p = sub.add_parser("show", help="Affiche la spec JSON (preset + surcharges)")
    p.add_argument("--preset")
    p.add_argument("--spec")
    p.add_argument("--set", action="append")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("metrics", help="Métriques immobilières (sans Blender)")
    p.add_argument("--preset")
    p.add_argument("--spec")
    p.add_argument("--set", action="append")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_metrics)

    p = sub.add_parser("build", help="Construit, rend et exporte un bâtiment")
    p.add_argument("--preset")
    p.add_argument("--spec")
    p.add_argument("--set", action="append", help="Surcharge : clé.pointée=valeur (JSON)")
    _add_engine_args(p)
    _add_output_args(p)
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("street", help="Génère une rue de bâtiments")
    p.add_argument("--preset", default="haussmann")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--gap", type=float, default=0.0)
    p.add_argument("--floors-min", type=int, default=5)
    p.add_argument("--floors-max", type=int, default=7)
    p.add_argument("--width-min", type=float, default=12.0)
    p.add_argument("--width-max", type=float, default=24.0)
    p.add_argument("--set", action="append")
    _add_engine_args(p)
    _add_output_args(p)
    p.set_defaults(fn=cmd_street)

    p = sub.add_parser("site", help="Modélise un site réel à partir d'une adresse (IGN, cadastre, OSM, orthophoto)")
    p.add_argument("--address", required=True)
    p.add_argument("--radius", type=float, default=80.0, help="Rayon des voisins (m)")
    p.add_argument("--no-context", action="store_true")
    p.add_argument("--no-ortho", action="store_true")
    p.add_argument("--no-build", action="store_true", help="Récupère les données et la spec sans lancer Blender")
    p.add_argument("--set", action="append", help="Surcharge du bâtiment cible : clé.pointée=valeur")
    _add_engine_args(p)
    _add_output_args(p)
    p.set_defaults(fn=cmd_site, views="street,perspective")
    p.set_defaults(fn=cmd_site)

    p = sub.add_parser("mcp", help="Lance le serveur MCP (arguments passés à blender-buildings-mcp)")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_mcp)

    p = sub.add_parser("api", help="Lance l'API HTTP (arguments passés à blender-buildings-api)")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_api)

    p = sub.add_parser("doctor", help="Vérifie l'installation (bpy, binaire, moteur)")
    _add_engine_args(p)
    p.set_defaults(fn=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
