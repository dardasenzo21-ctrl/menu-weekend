"""Presets de bâtiments : typologies courantes du marché immobilier français.

Chaque preset est un ``dict`` validé en ``BuildingSpec``. ``get_preset(name, overrides)``
permet d'ajuster n'importe quel champ (clés pointées : ``"roof.kind"``).
"""

from __future__ import annotations

from typing import Any

from .spec import BuildingSpec

PRESETS: dict[str, dict[str, Any]] = {
    "haussmann": {
        "name": "Immeuble haussmannien",
        "use": "residential",
        "footprint": {"kind": "rect", "width": 18.0, "depth": 14.0},
        "floors": 6,
        "floor_height": 3.2,
        "ground_floor": {"height": 4.2, "storefront": True, "glazing_ratio": 0.6, "material": "limestone"},
        "windows": {"style": "punched", "width": 1.3, "height": 2.3, "sill": 0.5, "bay_width": 3.0, "recess": 0.25, "frame_material": "frame_white"},
        "roof": {"kind": "mansard", "mansard_inset": 1.6, "mansard_height": 2.8, "height": 1.2, "dormers": True, "material": "zinc"},
        "balconies": {"floors": [2, 5], "depth": 0.8, "continuous": True, "material": "limestone", "railing_material": "metal_dark"},
        "facade": {"material": "limestone", "base_material": "stone_dark", "base_height": 0.8, "cornices": True, "cornice_floors": [1, 2, 5, 6], "cornice_depth": 0.3, "cornice_height": 0.25, "trim_material": "limestone"},
        "metadata": {"description": "Immeuble parisien 1860-1900 : pierre de taille, balcons filants aux 2e et 5e, toiture mansardée en zinc."},
    },
    "residential_modern": {
        "name": "Résidence contemporaine",
        "use": "residential",
        "footprint": {"kind": "L", "width": 28.0, "depth": 16.0, "wing_width": 10.0, "wing_depth": 7.0},
        "floors": 5,
        "floor_height": 2.9,
        "ground_floor": {"height": 3.4, "storefront": False, "material": "concrete"},
        "windows": {"style": "punched", "width": 1.8, "height": 2.15, "sill": 0.3, "bay_width": 3.6, "recess": 0.2, "frame_material": "frame_black"},
        "roof": {"kind": "parapet", "parapet_height": 1.0, "material": "concrete"},
        "balconies": {"floors": [1, 2, 3, 4], "depth": 1.5, "continuous": False, "material": "concrete", "railing_material": "frame_black"},
        "facade": {"material": "render_white", "cornices": False, "trim_material": "concrete"},
        "metadata": {"description": "Programme neuf de logements : enduit blanc, grandes baies, balcons, attique."},
    },
    "office": {
        "name": "Immeuble de bureaux",
        "use": "office",
        "footprint": {"kind": "rect", "width": 36.0, "depth": 18.0},
        "floors": 8,
        "floor_height": 3.6,
        "ground_floor": {"height": 4.5, "storefront": True, "glazing_ratio": 0.85, "material": "stone_dark"},
        "windows": {"style": "curtain", "mullion": 0.12, "spandrel": 0.9, "bay_width": 1.5, "recess": 0.05, "frame_material": "frame_bronze", "glass_material": "glass_tinted"},
        "roof": {"kind": "parapet", "parapet_height": 1.2, "material": "metal_dark"},
        "facade": {"material": "metal_dark", "cornices": False, "trim_material": "metal_dark"},
        "unit_average_area": 65.0,
        "metadata": {"description": "Bureaux tertiaires : mur-rideau à allèges opaques, trame 1,50 m, RDC hall vitré."},
    },
    "hotel": {
        "name": "Hôtel",
        "use": "hotel",
        "footprint": {"kind": "U", "width": 34.0, "depth": 20.0, "wing_width": 12.0, "wing_depth": 10.0},
        "floors": 7,
        "floor_height": 3.1,
        "ground_floor": {"height": 4.5, "storefront": True, "glazing_ratio": 0.75, "material": "stone_dark"},
        "windows": {"style": "punched", "width": 1.6, "height": 1.9, "sill": 0.6, "bay_width": 3.4, "recess": 0.2, "frame_material": "frame_bronze"},
        "roof": {"kind": "parapet", "parapet_height": 0.9, "material": "concrete"},
        "balconies": {"floors": [6], "depth": 1.2, "continuous": True, "material": "concrete", "railing_material": "frame_bronze"},
        "facade": {"material": "render_beige", "cornices": True, "cornice_floors": "top", "trim_material": "limestone"},
        "metadata": {"description": "Hôtel en U autour d'une cour : chambres régulières, terrasse en dernier étage."},
    },
    "logistics": {
        "name": "Entrepôt logistique",
        "use": "logistics",
        "footprint": {"kind": "rect", "width": 96.0, "depth": 48.0},
        "floors": 1,
        "floor_height": 10.0,
        "ground_floor": {"height": 11.0, "storefront": False, "material": "metal_light"},
        "windows": {"style": "ribbon", "height": 1.2, "sill": 7.5, "bay_width": 12.0, "mullion": 0.3, "recess": 0.05, "frame_material": "frame_black"},
        "roof": {"kind": "parapet", "parapet_height": 0.8, "material": "metal_light"},
        "facade": {"material": "metal_light", "base_material": "concrete", "base_height": 2.5, "cornices": False, "trim_material": "metal_light"},
        "site": {"ground": True, "ground_size": 260.0},
        "efficiency_ratio": 0.95,
        "metadata": {"description": "Entrepôt classe A : bardage métal, soubassement béton, bandeau vitré haut."},
    },
    "retail": {
        "name": "Commerce en pied d'immeuble",
        "use": "retail",
        "footprint": {"kind": "rect", "width": 24.0, "depth": 20.0},
        "floors": 2,
        "floor_height": 4.0,
        "ground_floor": {"height": 5.0, "storefront": True, "glazing_ratio": 0.9, "material": "stone_dark"},
        "windows": {"style": "ribbon", "height": 2.2, "sill": 0.9, "bay_width": 4.0, "mullion": 0.2, "recess": 0.1, "frame_material": "frame_black"},
        "roof": {"kind": "parapet", "parapet_height": 1.0, "material": "concrete"},
        "facade": {"material": "corten", "cornices": False, "trim_material": "metal_dark"},
        "efficiency_ratio": 0.9,
        "metadata": {"description": "Retail park / moyenne surface : vitrines généreuses, façade corten."},
    },
    "house": {
        "name": "Maison individuelle",
        "use": "residential",
        "footprint": {"kind": "rect", "width": 12.0, "depth": 9.0},
        "floors": 2,
        "floor_height": 2.7,
        "ground_floor": {"height": 2.8, "storefront": False},
        "windows": {"style": "punched", "width": 1.2, "height": 1.3, "sill": 0.9, "bay_width": 3.0, "recess": 0.15, "frame_material": "frame_white"},
        "roof": {"kind": "gable", "height": 3.2, "overhang": 0.5, "material": "terracotta_tile"},
        "facade": {"material": "render_beige", "cornices": False, "trim_material": "render_beige"},
        "site": {"ground": True, "ground_size": 60.0, "ground_material": "grass"},
        "unit_average_area": 120.0,
        "metadata": {"description": "Pavillon R+1 : enduit, toiture tuiles à deux pans."},
    },
    "mixed_use": {
        "name": "Immeuble mixte commerces + logements",
        "use": "mixed",
        "footprint": {"kind": "rect", "width": 30.0, "depth": 15.0},
        "floors": 7,
        "floor_height": 3.0,
        "ground_floor": {"height": 4.5, "storefront": True, "glazing_ratio": 0.8, "material": "concrete"},
        "windows": {"style": "punched", "width": 1.6, "height": 2.0, "sill": 0.4, "bay_width": 3.2, "recess": 0.2, "frame_material": "frame_black"},
        "roof": {"kind": "parapet", "parapet_height": 1.1, "material": "concrete"},
        "balconies": {"floors": [2, 3, 4, 5, 6], "depth": 1.4, "continuous": False, "material": "concrete", "railing_material": "frame_black"},
        "facade": {"material": "brick_red", "cornices": True, "cornice_floors": [1], "cornice_depth": 0.35, "cornice_height": 0.4, "trim_material": "concrete"},
        "metadata": {"description": "Rez-de-chaussée actif et logements en étages, brique et béton."},
    },
    "tower": {
        "name": "Tour tertiaire",
        "use": "office",
        "footprint": {"kind": "rect", "width": 32.0, "depth": 32.0},
        "floors": 30,
        "floor_height": 3.8,
        "ground_floor": {"height": 6.0, "storefront": True, "glazing_ratio": 0.9, "material": "stone_dark"},
        "windows": {"style": "curtain", "mullion": 0.1, "spandrel": 0.5, "bay_width": 1.35, "recess": 0.0, "frame_material": "frame_black", "glass_material": "glass_tinted"},
        "roof": {"kind": "parapet", "parapet_height": 2.0, "material": "metal_dark"},
        "facade": {"material": "metal_dark", "cornices": False, "trim_material": "metal_dark"},
        "site": {"ground": True, "ground_size": 200.0},
        "metadata": {"description": "IGH de bureaux, mur-rideau intégral."},
    },
}


def list_presets() -> list[dict[str, str]]:
    out = []
    for key, data in PRESETS.items():
        out.append(
            {
                "id": key,
                "name": data["name"],
                "use": data["use"],
                "description": data.get("metadata", {}).get("description", ""),
            }
        )
    return out


def get_preset(name: str, overrides: dict[str, Any] | None = None) -> BuildingSpec:
    if name not in PRESETS:
        raise KeyError(f"Preset inconnu : {name!r}. Disponibles : {', '.join(PRESETS)}")
    spec = BuildingSpec.model_validate(PRESETS[name])
    return spec.with_overrides(overrides)
