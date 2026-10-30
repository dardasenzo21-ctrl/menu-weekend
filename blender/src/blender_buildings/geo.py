"""Modélisation d'un site réel à partir d'une adresse (France) — Python pur, sans bpy.

Sources ouvertes interrogées :

* **Géocodage** : Base Adresse Nationale (api-adresse.data.gouv.fr), repli Nominatim (OpenStreetMap).
* **Bâtiments** : IGN BD TOPO® (WFS ``BDTOPO_V3:batiment``) : emprise au sol, hauteur à l'égout, nombre
  d'étages, usage, matériaux, nombre de logements.
* **Parcelle** : IGN Parcellaire Express (WFS ``CADASTRALPARCELS.PARCELLAIRE_EXPRESS:parcelle``) : contenance.
* **Tags OSM** (optionnel) : ``building:levels``, ``start_date``, ``architect``, ``name`` via Overpass.
* **Orthophoto** : IGN HR.ORTHOIMAGERY.ORTHOPHOTOS (WMS, Lambert-93) plaquée sur le plan de sol.

Le résultat est un ``SiteModel`` : la spec du bâtiment cible (emprise exacte en polygone), les specs des bâtiments
voisins (massing avec leurs vraies hauteurs), la parcelle, l'orthophoto et la liste des sources. Il est sérialisable en
JSON et construit par ``builder.build_site`` dans Blender.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field

from . import geometry
from .spec import BuildingSpec, Site

Point = tuple[float, float]
Fetcher = Callable[..., bytes]  # (url, headers, [retries, timeout]) -> contenu

USER_AGENT = "blender-buildings/1.0 (+https://github.com/dardasenzo21-ctrl/menu-weekend)"
IGN_WFS = "https://data.geopf.fr/wfs/ows"
IGN_WMS = "https://data.geopf.fr/wms-r/wms"
BAN_URL = "https://api-adresse.data.gouv.fr/search/"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = ("https://overpass.kumi.systems/api/interpreter", "https://lz4.overpass-api.de/api/interpreter", "https://overpass-api.de/api/interpreter")


# ----------------------------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------------------------
def default_fetcher(url: str, headers: dict[str, str] | None = None, retries: int = 2, timeout: float = 45.0) -> bytes:
    import requests

    h = {"User-Agent": USER_AGENT}
    h.update(headers or {})
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=h, timeout=timeout)
            r.raise_for_status()
            return r.content
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Échec HTTP après {retries} tentatives : {url} ({last})")


def _url(base: str, params: dict[str, Any]) -> str:
    return base + "?" + urllib.parse.urlencode(params)


# ----------------------------------------------------------------------------------------------
# Projection locale (mètres, nord vers +Y) — Lambert-93 via pyproj, repli équirectangulaire
# ----------------------------------------------------------------------------------------------
class LocalProjection:
    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        try:
            from pyproj import Transformer

            self._fwd = Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)
            self.x0, self.y0 = self._fwd.transform(lon0, lat0)
            self.crs = "EPSG:2154"
        except Exception:  # pyproj absent
            self._fwd = None
            self.x0 = self.y0 = 0.0
            self.crs = "equirectangular"

    def to_local(self, lon: float, lat: float) -> Point:
        if self._fwd is not None:
            x, y = self._fwd.transform(lon, lat)
            return (x - self.x0, y - self.y0)
        return ((lon - self.lon0) * math.cos(math.radians(self.lat0)) * 111320.0, (lat - self.lat0) * 110574.0)

    def l93_bbox(self, half_size_m: float) -> tuple[float, float, float, float]:
        return (self.x0 - half_size_m, self.y0 - half_size_m, self.x0 + half_size_m, self.y0 + half_size_m)


# ----------------------------------------------------------------------------------------------
# Modèles
# ----------------------------------------------------------------------------------------------
class GeoBuilding(BaseModel):
    """Bâtiment brut (coordonnées locales en mètres)."""

    id: str
    ring: list[Point]
    height_m: float | None = None
    levels: int | None = None
    usage: str | None = None
    dwellings: int | None = None
    wall_material: str | None = None
    roof_material: str | None = None
    ground_altitude_m: float | None = None
    tags: dict[str, Any] = Field(default_factory=dict)
    source: str = "IGN BD TOPO"
    is_target: bool = False


class OrthoImage(BaseModel):
    path: str
    half_size_m: float
    crs: str = "EPSG:2154"
    bbox: tuple[float, float, float, float]
    pixels: int


class SiteModel(BaseModel):
    address: str
    label: str
    lat: float
    lon: float
    target: BuildingSpec
    context: list[BuildingSpec] = Field(default_factory=list)
    buildings_raw: list[GeoBuilding] = Field(default_factory=list)
    parcel: dict[str, Any] | None = None
    ortho: OrthoImage | None = None
    facade_azimuth_deg: float = Field(0.0, description="D'où regarder la façade sur rue : 0 = depuis le sud, 90 = depuis l'est (sens horaire)")
    street_distance_m: float = Field(12.0, description="Distance estimée façade → point adresse (largeur de rue)")
    sources: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------------------------------
# Récupération des données
# ----------------------------------------------------------------------------------------------
def geocode(address: str, fetch: Fetcher = default_fetcher) -> dict[str, Any]:
    """Retourne {lat, lon, label, source}."""
    errors = []
    try:
        data = json.loads(fetch(_url(BAN_URL, {"q": address, "limit": 1}), None))
        feat = data["features"][0]
        lon, lat = feat["geometry"]["coordinates"]
        return {"lat": float(lat), "lon": float(lon), "label": feat["properties"]["label"], "source": "BAN (api-adresse.data.gouv.fr)"}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"BAN : {exc}")
    try:
        data = json.loads(fetch(_url(NOMINATIM_URL, {"q": address, "format": "json", "limit": 1}), None))
        hit = data[0]
        return {"lat": float(hit["lat"]), "lon": float(hit["lon"]), "label": hit["display_name"], "source": "Nominatim (OpenStreetMap)"}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Nominatim : {exc}")
    raise RuntimeError("Géocodage impossible — " + " ; ".join(errors))


def _bbox_latlon(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    dlat = radius_m / 110574.0
    dlon = radius_m / (111320.0 * math.cos(math.radians(lat)))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


def fetch_ign_buildings(lat: float, lon: float, radius_m: float, fetch: Fetcher = default_fetcher) -> list[dict[str, Any]]:
    b = _bbox_latlon(lat, lon, radius_m)
    url = _url(IGN_WFS, {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": "BDTOPO_V3:batiment", "OUTPUTFORMAT": "application/json", "COUNT": 2000, "BBOX": f"{b[0]},{b[1]},{b[2]},{b[3]},urn:ogc:def:crs:EPSG::4326"})
    return json.loads(fetch(url, None)).get("features", [])


def fetch_ign_parcels(lat: float, lon: float, radius_m: float, fetch: Fetcher = default_fetcher) -> list[dict[str, Any]]:
    b = _bbox_latlon(lat, lon, radius_m)
    url = _url(IGN_WFS, {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": "CADASTRALPARCELS.PARCELLAIRE_EXPRESS:parcelle", "OUTPUTFORMAT": "application/json", "COUNT": 200, "BBOX": f"{b[0]},{b[1]},{b[2]},{b[3]},urn:ogc:def:crs:EPSG::4326"})
    return json.loads(fetch(url, None)).get("features", [])


def fetch_osm_buildings(lat: float, lon: float, radius_m: float, fetch: Fetcher = default_fetcher) -> list[dict[str, Any]]:
    b = _bbox_latlon(lat, lon, radius_m)
    q = f'[out:json][timeout:60];(way["building"]({b[0]},{b[1]},{b[2]},{b[3]});relation["building"]({b[0]},{b[1]},{b[2]},{b[3]}););out body geom;'
    for base in OVERPASS_URLS:
        try:
            return json.loads(fetch(_url(base, {"data": q}), None, 1, 60.0)).get("elements", [])  # type: ignore[call-arg]
        except Exception:  # noqa: BLE001
            continue
    return []


def fetch_orthophoto(proj: LocalProjection, half_size_m: float, path: str, pixels: int = 2048, fetch: Fetcher = default_fetcher) -> OrthoImage:
    bbox = proj.l93_bbox(half_size_m)
    url = _url(IGN_WMS, {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": "HR.ORTHOIMAGERY.ORTHOPHOTOS", "STYLES": "", "CRS": "EPSG:2154", "BBOX": ",".join(f"{v:.2f}" for v in bbox), "WIDTH": pixels, "HEIGHT": pixels, "FORMAT": "image/jpeg"})
    data = fetch(url, None)
    if not data.startswith(b"\xff\xd8"):
        raise RuntimeError("La réponse WMS n'est pas un JPEG (service indisponible ?)")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return OrthoImage(path=os.path.abspath(path), half_size_m=half_size_m, bbox=bbox, pixels=pixels)


# ----------------------------------------------------------------------------------------------
# Géométrie
# ----------------------------------------------------------------------------------------------
def _lonlat(c: list[float]) -> Point:
    """Ordre des axes WFS/EPSG:4326 ambigu selon les services : en Europe |lat| > |lon|, on s'en sert."""
    a, b = float(c[0]), float(c[1])
    return (b, a) if abs(a) > abs(b) else (a, b)


def _point_in_ring(pt: Point, ring: list[Point]) -> bool:
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-18) + x1:
            inside = not inside
    return inside


def _clean_ring(ring: list[Point], min_edge: float = 0.25) -> list[Point]:
    """Supprime le point de fermeture, les doublons et les sommets quasi colinéaires très proches."""
    pts: list[Point] = []
    for p in ring:
        if pts and math.dist(pts[-1], p) < min_edge:
            continue
        pts.append((float(p[0]), float(p[1])))
    while len(pts) > 1 and math.dist(pts[0], pts[-1]) < min_edge:
        pts.pop()
    out: list[Point] = []
    n = len(pts)
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cross) < 1e-3 and math.dist(a, c) < 2.0:  # sommet inutile
            continue
        out.append(b)
    return geometry.ensure_ccw(out) if len(out) >= 3 else []


def _rings_of(geom: dict[str, Any]) -> list[list[list[float]]]:
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [poly[0] for poly in geom["coordinates"]]
    return []


def parse_ign_buildings(features: list[dict[str, Any]], proj: LocalProjection, lat: float, lon: float) -> list[GeoBuilding]:
    out: list[GeoBuilding] = []
    for f in features:
        p = f.get("properties", {})
        for k, ring in enumerate(_rings_of(f["geometry"])):
            local = [proj.to_local(*_lonlat(c)) for c in ring]
            clean = _clean_ring(local)
            if len(clean) < 3 or geometry.area(clean) < 12.0:
                continue
            target = _point_in_ring(proj.to_local(lon, lat), clean)
            out.append(
                GeoBuilding(
                    id=f"{f.get('id', 'bat')}{'' if k == 0 else f'-{k}'}",
                    ring=clean,
                    height_m=p.get("hauteur"),
                    levels=p.get("nombre_d_etages"),
                    usage=p.get("usage_1"),
                    dwellings=p.get("nombre_de_logements"),
                    wall_material=p.get("materiaux_des_murs"),
                    roof_material=p.get("materiaux_de_la_toiture"),
                    ground_altitude_m=p.get("altitude_minimale_sol"),
                    tags={k2: v for k2, v in p.items() if k2 in ("cleabs", "nature", "date_d_apparition", "origine_du_batiment", "identifiants_rnb") and v},
                    is_target=target,
                )
            )
    return out


def match_osm_tags(buildings: list[GeoBuilding], elements: list[dict[str, Any]], proj: LocalProjection) -> None:
    """Attache les tags OSM (niveaux, date, architecte, nom) au bâtiment IGN dont l'emprise contient leur centre."""
    for e in elements:
        geom = e.get("geometry") or []
        tags = e.get("tags") or {}
        if not geom or not tags:
            continue
        pts = [proj.to_local(g["lon"], g["lat"]) for g in geom if "lon" in g]
        if not pts:
            continue
        c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        keep = {k: v for k, v in tags.items() if k in ("building", "building:levels", "height", "start_date", "architect", "name", "roof:shape", "building:colour", "addr:housenumber", "addr:street")}
        if not keep:
            continue
        for b in buildings:
            if _point_in_ring(c, b.ring):
                b.tags.update({f"osm:{k}": v for k, v in keep.items()})
                b.tags["osm:id"] = f"{e['type']}/{e['id']}"
                if b.levels is None and keep.get("building:levels", "").isdigit():
                    b.levels = int(keep["building:levels"])
                break


# ----------------------------------------------------------------------------------------------
# Du bâtiment brut à la spec paramétrique
# ----------------------------------------------------------------------------------------------
def _levels_and_height(b: GeoBuilding) -> tuple[int, float]:
    h = b.height_m or (b.levels or 4) * 3.0
    levels = b.levels or max(1, round(h / 3.0))
    if h / max(levels, 1) > 11.0:  # halle, église, atrium : un « étage » IGN de 20 m → on découpe
        levels = max(levels, math.ceil(h / 4.0))
    levels = max(1, min(levels, 60))
    return levels, h


def building_to_spec(b: GeoBuilding, name: str, detailed: bool, overrides: dict[str, Any] | None = None) -> BuildingSpec:
    """Spec paramétrique « parisienne » : façade pierre, fenêtres percées, zinc. Les murs atteignent la hauteur IGN (égout)."""
    levels, h = _levels_and_height(b)
    cx, cy = geometry.centroid(b.ring)
    ring = [(x - cx, y - cy) for x, y in b.ring]
    ground_h = 3.6 if levels > 1 else h
    floor_h = (h - ground_h) / (levels - 1) if levels > 1 else 3.0
    if floor_h < 2.2:  # hauteur IGN incohérente avec le nombre d'étages : on répartit
        floor_h = max(2.2, h / levels)
        ground_h = floor_h
    usage = (b.usage or "").lower()
    use = "office" if "commercial" in usage or "industriel" in usage else "residential"
    if "résidentiel" in usage:
        use = "residential"
    storefront = detailed and levels >= 3
    window_h = min(2.2, floor_h - 0.7)
    data: dict[str, Any] = {
        "name": name,
        "use": use,
        "footprint": {"kind": "polygon", "points": ring},
        "floors": levels,
        "floor_height": round(floor_h, 3),
        "ground_floor": {"height": round(ground_h, 3), "storefront": storefront, "glazing_ratio": 0.55, "material": "limestone" if detailed else None},
        "windows": {"style": "punched", "width": 1.25, "height": round(window_h, 2), "sill": round(min(0.6, max(0.1, floor_h - window_h - 0.35)), 2), "bay_width": 2.9, "recess": 0.22, "frame_material": "frame_white"},
        "facade": {"material": "limestone" if detailed else "render_beige", "base_material": "stone_dark" if detailed else None, "base_height": 0.8, "cornices": True, "cornice_floors": "top", "cornice_depth": 0.3, "cornice_height": 0.25, "trim_material": "limestone"},
        "site": {"ground": False},
        "position": (round(cx, 3), round(cy, 3), 0.0),
        "metadata": {"source": b.source, "ign_height_m": b.height_m, "ign_levels": b.levels, "ign_usage": b.usage, "ign_dwellings": b.dwellings, **b.tags},
    }
    if detailed and levels >= 5:
        data["roof"] = {"kind": "mansard", "mansard_inset": 1.5, "mansard_height": 2.6, "height": 1.0, "dormers": True, "material": "zinc"}
        data["balconies"] = {"floors": [f for f in (2, levels - 1) if 1 <= f < levels], "depth": 0.7, "continuous": True, "material": "limestone", "railing_material": "metal_dark"}
        data["facade"]["cornice_floors"] = sorted({1, 2, levels - 1, levels} - {0})
    elif detailed:
        data["roof"] = {"kind": "hip", "height": 2.5, "overhang": 0.3, "material": "zinc"}
    else:
        data["roof"] = {"kind": "parapet", "parapet_height": 0.6, "parapet_thickness": 0.3, "material": "zinc" if levels >= 4 else "concrete"}
    spec = BuildingSpec.model_validate(data)
    return spec.with_overrides(overrides)


def site_from_address(address: str, radius_m: float = 80.0, context: bool = True, orthophoto: bool = True, ortho_dir: str | None = None, osm: bool = True, overrides: dict[str, Any] | None = None, fetch: Fetcher = default_fetcher) -> SiteModel:
    """Pipeline complet : adresse → SiteModel (specs prêtes à construire)."""
    g = geocode(address, fetch)
    lat, lon = g["lat"], g["lon"]
    proj = LocalProjection(lat, lon)
    sources = [g["source"], "IGN BD TOPO® (bâtiments : emprise, hauteur, étages, usage)"]
    notes: list[str] = []

    feats = fetch_ign_buildings(lat, lon, max(radius_m, 30.0) + 20.0, fetch)
    buildings = parse_ign_buildings(feats, proj, lat, lon)
    if not buildings:
        raise RuntimeError("Aucun bâtiment IGN autour de l'adresse")
    targets = [b for b in buildings if b.is_target]
    if not targets:
        # l'adresse tombe dans la rue : bâtiment le plus proche
        nearest = min(buildings, key=lambda b: math.dist(geometry.centroid(b.ring), (0.0, 0.0)))
        nearest.is_target = True
        targets = [nearest]
        notes.append("Le point adresse ne tombe dans aucune emprise : bâtiment le plus proche retenu.")
    target_raw = targets[0]

    parcel = None
    try:
        for f in fetch_ign_parcels(lat, lon, 25.0, fetch):
            for ring in _rings_of(f["geometry"]):
                local = _clean_ring([proj.to_local(*_lonlat(c)) for c in ring])
                if local and _point_in_ring((0.0, 0.0), local):
                    p = f["properties"]
                    parcel = {"id": p.get("idu"), "section": p.get("section"), "numero": p.get("numero"), "area_m2": p.get("contenance"), "ring": local}
        if parcel:
            sources.append("IGN Parcellaire Express (parcelle cadastrale)")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Parcelle indisponible : {exc}")

    if osm:
        try:
            elements = fetch_osm_buildings(lat, lon, radius_m + 20.0, fetch)
            if elements:
                match_osm_tags(buildings, elements, proj)
                sources.append("OpenStreetMap (tags : niveaux, dates, architectes, noms)")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"OSM indisponible : {exc}")

    target_over = dict(overrides or {})
    if parcel and parcel.get("area_m2"):
        target_over.setdefault("site.parcel_area", float(parcel["area_m2"]))
    target_spec = building_to_spec(target_raw, _target_name(address, target_raw), detailed=True, overrides=target_over)

    ctx_specs: list[BuildingSpec] = []
    if context:
        for i, b in enumerate(buildings):
            if b.is_target:
                continue
            if math.dist(geometry.centroid(b.ring), (0.0, 0.0)) > radius_m:
                continue
            try:
                ctx_specs.append(building_to_spec(b, f"Voisin {i + 1}", detailed=False))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"Voisin {b.id} ignoré : {exc}")

    ortho = None
    if orthophoto:
        try:
            half = max(radius_m + 30.0, 60.0)
            path = os.path.join(ortho_dir or os.getcwd(), f"ortho_{_slug(address)}.jpg")
            ortho = fetch_orthophoto(proj, half, path, fetch=fetch)
            sources.append("IGN orthophoto HR (plan de sol)")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Orthophoto indisponible : {exc}")

    # Le point adresse (origine locale) est dans la rue, devant la façade : il donne l'orientation de la façade.
    cx, cy = geometry.centroid(target_raw.ring)
    dx, dy = -cx, -cy
    azimuth = math.degrees(math.atan2(dx, -dy)) % 360.0 if math.hypot(dx, dy) > 0.5 else 0.0
    street_distance = max(6.0, min(25.0, 2.0 * math.hypot(dx, dy)))
    return SiteModel(address=address, label=g["label"], lat=lat, lon=lon, target=target_spec, context=ctx_specs, buildings_raw=buildings, parcel=parcel, ortho=ortho, facade_azimuth_deg=round(azimuth, 1), street_distance_m=round(street_distance, 1), sources=sources, notes=notes)


def _slug(s: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()[:60]


def _target_name(address: str, b: GeoBuilding) -> str:
    name = b.tags.get("osm:name")
    return str(name) if name else address.strip()[:60]
