"""Métriques immobilières et géométriques calculées à partir d'une ``BuildingSpec`` (sans bpy).

Vocabulaire (France) :

* **emprise au sol** : surface de l'empreinte du bâtiment.
* **surface de plancher (SDP)** : somme des surfaces de chaque niveau (approximée par emprise × niveaux).
* **surface utile / habitable** : SDP × ``efficiency_ratio``.
* **CES** (coefficient d'emprise au sol) : emprise / parcelle.
* **densité** : SDP / parcelle.
"""

from __future__ import annotations

from typing import Any

from . import geometry
from .spec import BuildingSpec


def _window_counts(spec: BuildingSpec) -> tuple[int, float]:
    """Retourne (nombre de fenêtres d'étage courant, surface vitrée totale en m²)."""
    pts = spec.footprint.polygon()
    w = spec.windows
    gf = spec.ground_floor
    n_windows = 0
    glazing = 0.0
    for (a, b) in geometry.edges(pts):
        length = geometry.perimeter([a, b]) / 2.0  # distance a-b
        bays = max(1, round(length / w.bay_width))
        bay = length / bays
        # étages courants
        per_floor_glass = 0.0
        if w.style == "punched":
            per_floor_glass = bays * w.width * w.height
            n_windows += bays * (spec.floors - 1)
        elif w.style == "ribbon":
            per_floor_glass = bays * max(0.0, bay - w.mullion) * w.height
            n_windows += bays * (spec.floors - 1)
        elif w.style == "curtain":
            per_floor_glass = bays * max(0.0, bay - w.mullion) * max(0.0, spec.floor_height - w.spandrel)
            n_windows += bays * (spec.floors - 1)
        glazing += per_floor_glass * (spec.floors - 1)
        # RDC
        if gf.storefront:
            glazing += bays * bay * gf.glazing_ratio * max(0.0, gf.height - 0.9)
        elif w.style != "none":
            glazing += per_floor_glass
    return n_windows, glazing


def compute_metrics(spec: BuildingSpec) -> dict[str, Any]:
    pts = spec.footprint.polygon()
    footprint_area = geometry.area(pts)
    perim = geometry.perimeter(pts)
    wall_h = spec.wall_height()
    total_h = spec.total_height()
    gfa = footprint_area * spec.floors
    basement_area = footprint_area * spec.basement_levels
    usable = gfa * spec.efficiency_ratio
    n_windows, glazing_area = _window_counts(spec)
    facade_area = perim * wall_h
    roof_volume = 0.0
    r = spec.roof
    if r.kind in ("hip", "gable"):
        roof_volume = footprint_area * r.height / 2.0
    elif r.kind == "mansard":
        roof_volume = footprint_area * r.mansard_height * 0.8 + footprint_area * r.height / 2.0
    volume = footprint_area * wall_h + roof_volume

    out: dict[str, Any] = {
        "name": spec.name,
        "use": spec.use,
        "floors": spec.floors,
        "basement_levels": spec.basement_levels,
        "footprint_area_m2": round(footprint_area, 2),
        "perimeter_m": round(perim, 2),
        "wall_height_m": round(wall_h, 2),
        "total_height_m": round(total_h, 2),
        "gross_floor_area_m2": round(gfa, 2),
        "basement_area_m2": round(basement_area, 2),
        "usable_area_m2": round(usable, 2),
        "facade_area_m2": round(facade_area, 2),
        "glazing_area_m2": round(glazing_area, 2),
        "glazing_ratio": round(glazing_area / facade_area, 3) if facade_area else 0.0,
        "window_count": n_windows,
        "volume_m3": round(volume, 1),
        "roof_kind": r.kind,
    }
    if spec.use in ("residential", "mixed", "hotel"):
        per_unit = spec.unit_average_area if spec.use != "hotel" else 28.0
        units = usable / per_unit
        if spec.use == "mixed":
            units = (usable - footprint_area * spec.efficiency_ratio) / per_unit  # RDC commercial exclu
        out["estimated_units"] = max(0, int(units))
        out["unit_label"] = "chambres" if spec.use == "hotel" else "logements"
    if spec.use in ("office", "mixed"):
        out["estimated_workstations"] = int(usable / 12.0) if spec.use == "office" else int(footprint_area * spec.efficiency_ratio / 12.0)
    if spec.site.parcel_area:
        out["parcel_area_m2"] = spec.site.parcel_area
        out["site_coverage_ratio"] = round(footprint_area / spec.site.parcel_area, 3)
        out["density_ratio"] = round(gfa / spec.site.parcel_area, 3)
    if spec.price_per_m2:
        out["price_per_m2_eur"] = spec.price_per_m2
        out["estimated_value_eur"] = round(usable * spec.price_per_m2, 0)
    return out


def format_metrics(m: dict[str, Any]) -> str:
    """Résumé lisible en français."""
    lines = [
        f"{m['name']} — {m['use']} — {m['floors']} niveaux, {m['total_height_m']} m",
        f"Emprise au sol : {m['footprint_area_m2']} m² | Surface de plancher : {m['gross_floor_area_m2']} m² | Surface utile : {m['usable_area_m2']} m²",
        f"Façades : {m['facade_area_m2']} m² dont vitrage {m['glazing_area_m2']} m² ({m['glazing_ratio'] * 100:.0f} %), {m['window_count']} fenêtres",
        f"Volume : {m['volume_m3']} m³ | Toiture : {m['roof_kind']}",
    ]
    if "estimated_units" in m:
        lines.append(f"≈ {m['estimated_units']} {m['unit_label']}")
    if "estimated_workstations" in m:
        lines.append(f"≈ {m['estimated_workstations']} postes de travail")
    if "site_coverage_ratio" in m:
        lines.append(f"Parcelle {m['parcel_area_m2']} m² : CES {m['site_coverage_ratio']}, densité {m['density_ratio']}")
    if "estimated_value_eur" in m:
        lines.append(f"Valeur estimée : {m['estimated_value_eur']:,.0f} € ({m['price_per_m2_eur']} €/m²)".replace(",", " "))
    return "\n".join(lines)
