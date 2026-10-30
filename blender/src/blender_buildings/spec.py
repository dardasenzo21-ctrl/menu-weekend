"""Modèles de données (Pydantic) décrivant un bâtiment paramétrique.

Toutes les dimensions sont en **mètres**. L'axe Z est vertical, le niveau 0 est le sol.
Un ``BuildingSpec`` est entièrement sérialisable en JSON : c'est le contrat commun
entre le CLI, l'API HTTP, le serveur MCP et le moteur Blender.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Point = tuple[float, float]

MaterialName = Literal[
    "limestone",        # pierre de taille (Haussmann)
    "render_white",     # enduit blanc
    "render_beige",     # enduit beige
    "concrete",         # béton brut
    "brick_red",        # brique rouge
    "brick_dark",       # brique sombre
    "glass",            # vitrage
    "glass_tinted",     # vitrage teinté (bureaux)
    "zinc",             # zinc (toiture parisienne)
    "slate",            # ardoise
    "terracotta_tile",  # tuile terre cuite
    "metal_dark",       # bardage métal anthracite
    "metal_light",      # bardage métal clair (logistique)
    "wood",             # bardage bois
    "corten",           # acier corten
    "frame_black",      # menuiserie noire
    "frame_white",      # menuiserie blanche
    "frame_bronze",     # menuiserie bronze
    "asphalt",          # sol / voirie
    "grass",            # pelouse
    "stone_dark",       # soubassement granit
]

UseType = Literal["residential", "office", "hotel", "logistics", "retail", "mixed"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Footprint(_Model):
    """Emprise au sol du bâtiment.

    * ``rect`` : rectangle ``width`` × ``depth`` centré sur l'origine.
    * ``L`` : rectangle auquel on retire un coin (``wing_width`` × ``wing_depth``) au nord-est.
    * ``U`` : rectangle avec une cour ouverte au nord (``wing_width`` = largeur de la cour).
    * ``polygon`` : polygone quelconque (``points``, sens anti-horaire, non auto-intersectant).
    """

    kind: Literal["rect", "L", "U", "polygon"] = "rect"
    width: float = Field(20.0, gt=0, description="Largeur (axe X) en m")
    depth: float = Field(12.0, gt=0, description="Profondeur (axe Y) en m")
    wing_width: float = Field(8.0, gt=0, description="Largeur de l'aile / cour (L, U)")
    wing_depth: float = Field(6.0, gt=0, description="Profondeur de l'aile / cour (L, U)")
    points: list[Point] | None = Field(None, description="Sommets du polygone (kind=polygon)")

    @model_validator(mode="after")
    def _check(self) -> "Footprint":
        if self.kind == "polygon":
            if not self.points or len(self.points) < 3:
                raise ValueError("Un polygone requiert au moins 3 points")
        if self.kind in ("L", "U"):
            if self.wing_width >= self.width:
                raise ValueError("wing_width doit être inférieur à width")
            if self.wing_depth >= self.depth:
                raise ValueError("wing_depth doit être inférieur à depth")
        return self

    def polygon(self) -> list[Point]:
        """Retourne l'emprise comme polygone anti-horaire, centré sur l'origine."""
        from . import geometry

        w, d = self.width / 2.0, self.depth / 2.0
        if self.kind == "rect":
            pts = [(-w, -d), (w, -d), (w, d), (-w, d)]
        elif self.kind == "L":
            ww, wd = self.wing_width, self.wing_depth
            pts = [(-w, -d), (w, -d), (w, d - wd), (w - ww, d - wd), (w - ww, d), (-w, d)]
        elif self.kind == "U":
            cw, cd = self.wing_width / 2.0, self.wing_depth
            pts = [(-w, -d), (w, -d), (w, d), (cw, d), (cw, d - cd), (-cw, d - cd), (-cw, d), (-w, d)]
        else:
            pts = [tuple(p) for p in self.points or []]
        return geometry.ensure_ccw(pts)


class Windows(_Model):
    """Fenêtres d'un étage courant."""

    style: Literal["punched", "ribbon", "curtain", "none"] = Field(
        "punched",
        description="punched = fenêtres percées ; ribbon = bandeau ; curtain = mur-rideau ; none = aveugle",
    )
    width: float = Field(1.2, gt=0, description="Largeur d'une fenêtre (punched)")
    height: float = Field(1.5, gt=0, description="Hauteur d'une fenêtre")
    sill: float = Field(0.9, ge=0, description="Hauteur d'allège (bas de la fenêtre)")
    bay_width: float = Field(3.0, gt=0.5, description="Largeur de travée (espacement des fenêtres)")
    recess: float = Field(0.15, ge=0, le=1.0, description="Profondeur de l'embrasure")
    frame: float = Field(0.06, ge=0, le=0.3, description="Épaisseur du cadre de menuiserie")
    mullion: float = Field(0.15, ge=0, description="Largeur de meneau (ribbon/curtain)")
    spandrel: float = Field(0.8, ge=0, description="Hauteur d'allège opaque (curtain)")
    frame_material: MaterialName = "frame_white"
    glass_material: MaterialName = "glass"


class GroundFloor(_Model):
    """Rez-de-chaussée (souvent plus haut, commercial)."""

    height: float = Field(4.0, gt=1.5)
    storefront: bool = Field(True, description="Vitrines commerciales au lieu de fenêtres")
    glazing_ratio: float = Field(0.7, ge=0, le=0.95, description="Part vitrée de chaque travée (storefront)")
    material: MaterialName | None = Field(None, description="Matériau du RDC (défaut : façade)")
    entrance_width: float = Field(2.4, gt=0)


class Roof(_Model):
    """Toiture."""

    kind: Literal["flat", "parapet", "hip", "gable", "mansard"] = "flat"
    height: float = Field(3.0, ge=0, description="Hauteur du comble (hip/gable/mansard)")
    parapet_height: float = Field(0.9, ge=0)
    parapet_thickness: float = Field(0.3, gt=0)
    overhang: float = Field(0.4, ge=0, description="Débord de toit (hip/gable)")
    mansard_inset: float = Field(1.2, gt=0, description="Retrait du brisis (mansard)")
    mansard_height: float = Field(2.6, gt=0, description="Hauteur du brisis (mansard)")
    dormers: bool = Field(True, description="Lucarnes sur le brisis (mansard)")
    material: MaterialName = "zinc"


class Balconies(_Model):
    """Balcons (numéros d'étages : 1 = premier étage au-dessus du RDC)."""

    floors: list[int] = Field(default_factory=list)
    depth: float = Field(0.9, gt=0)
    slab_thickness: float = Field(0.18, gt=0)
    railing_height: float = Field(1.0, gt=0)
    continuous: bool = Field(True, description="Balcon filant sur toute la façade")
    material: MaterialName = "limestone"
    railing_material: MaterialName = "metal_dark"


class Facade(_Model):
    material: MaterialName = "limestone"
    base_material: MaterialName | None = Field(None, description="Soubassement (bas du RDC)")
    base_height: float = Field(0.6, ge=0)
    cornices: bool = Field(True, description="Corniches / bandeaux entre étages")
    cornice_floors: list[int] | Literal["all", "top"] = Field("top", description="Étages portant une corniche")
    cornice_depth: float = Field(0.3, ge=0)
    cornice_height: float = Field(0.25, gt=0)
    trim_material: MaterialName = "limestone"
    pilasters: bool = Field(False, description="Pilastres entre travées du RDC")


class Site(_Model):
    ground: bool = True
    ground_size: float = Field(120.0, gt=0, description="Côté du plan de sol")
    ground_material: MaterialName = "asphalt"
    parcel_area: float | None = Field(None, gt=0, description="Surface de parcelle (m²) pour CES / densité")


class BuildingSpec(_Model):
    """Spécification complète d'un bâtiment."""

    name: str = Field("Building", min_length=1, max_length=60)
    use: UseType = "residential"
    footprint: Footprint = Field(default_factory=Footprint)
    floors: int = Field(6, ge=1, le=120, description="Nombre de niveaux hors sol, RDC inclus")
    floor_height: float = Field(3.0, gt=2.0, le=12.0, description="Hauteur d'un étage courant")
    basement_levels: int = Field(0, ge=0, le=6, description="Niveaux en sous-sol (métriques uniquement)")
    ground_floor: GroundFloor = Field(default_factory=GroundFloor)
    windows: Windows = Field(default_factory=Windows)
    roof: Roof = Field(default_factory=Roof)
    balconies: Balconies = Field(default_factory=Balconies)
    facade: Facade = Field(default_factory=Facade)
    site: Site = Field(default_factory=Site)
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_deg: float = Field(0.0, description="Rotation autour de Z")
    seed: int = Field(0, ge=0)
    unit_average_area: float = Field(65.0, gt=10, description="Surface moyenne d'un logement (m²) pour les métriques")
    efficiency_ratio: float = Field(0.85, gt=0.3, le=1.0, description="Surface utile / surface de plancher")
    price_per_m2: float | None = Field(None, gt=0, description="Prix €/m² pour estimer la valeur (optionnel)")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name vide")
        return v

    @model_validator(mode="after")
    def _check(self) -> "BuildingSpec":
        fh = self.floor_height
        w = self.windows
        if w.style == "punched" and w.sill + w.height > fh - 0.2:
            raise ValueError(
                f"Fenêtre trop haute : allège {w.sill} + hauteur {w.height} dépasse l'étage ({fh} m)"
            )
        if w.style == "punched" and w.width >= w.bay_width:
            raise ValueError("windows.width doit être inférieur à windows.bay_width")
        for f in self.balconies.floors:
            if f < 1 or f >= self.floors:
                raise ValueError(f"Étage de balcon invalide : {f} (1..{self.floors - 1})")
        if isinstance(self.facade.cornice_floors, list):
            for f in self.facade.cornice_floors:
                if f < 1 or f > self.floors:
                    raise ValueError(f"Étage de corniche invalide : {f}")
        return self

    # ---- aides géométriques ---------------------------------------------------------------
    def floor_levels(self) -> list[float]:
        """Altitudes du plancher de chaque niveau (index 0 = RDC)."""
        levels = [0.0]
        z = self.ground_floor.height
        for _ in range(1, self.floors):
            levels.append(z)
            z += self.floor_height
        return levels

    def wall_height(self) -> float:
        """Hauteur des murs (acrotère / toiture exclus)."""
        return self.ground_floor.height + self.floor_height * (self.floors - 1)

    def total_height(self) -> float:
        h = self.wall_height()
        r = self.roof
        if r.kind == "parapet":
            return h + r.parapet_height
        if r.kind in ("hip", "gable"):
            return h + r.height
        if r.kind == "mansard":
            return h + r.mansard_height + r.height
        return h

    def with_overrides(self, overrides: dict[str, Any] | None) -> "BuildingSpec":
        """Retourne une copie avec des surcharges (fusion profonde, clés pointées acceptées)."""
        if not overrides:
            return self
        data = self.model_dump()
        for key, value in overrides.items():
            _deep_set(data, key, value)
        # Si le nombre d'étages baisse, on élague les balcons/corniches devenus hors plage
        # plutôt que de rejeter la surcharge (ergonomie des appels « floors: 4 » sur un preset).
        floors = int(data.get("floors", self.floors))
        bal = data.get("balconies", {})
        if isinstance(bal.get("floors"), list):
            bal["floors"] = [f for f in bal["floors"] if 1 <= f < floors]
        fac = data.get("facade", {})
        if isinstance(fac.get("cornice_floors"), list):
            fac["cornice_floors"] = [f for f in fac["cornice_floors"] if 1 <= f <= floors]
        return BuildingSpec.model_validate(data)


class BlockSpec(_Model):
    """Un îlot : plusieurs bâtiments positionnés explicitement."""

    name: str = "Block"
    buildings: list[BuildingSpec] = Field(default_factory=list, min_length=1)
    site: Site = Field(default_factory=lambda: Site(ground_size=200.0))


class StreetSpec(_Model):
    """Génération d'une rue : N bâtiments alignés, variés par ``seed``."""

    name: str = "Street"
    preset: str = "haussmann"
    count: int = Field(5, ge=1, le=60)
    gap: float = Field(0.0, ge=0, description="Espace entre bâtiments")
    width_range: tuple[float, float] = (12.0, 24.0)
    floors_range: tuple[int, int] = (5, 7)
    seed: int = 1
    overrides: dict[str, Any] = Field(default_factory=dict)
    site: Site = Field(default_factory=lambda: Site(ground_size=200.0))

    @model_validator(mode="after")
    def _check(self) -> "StreetSpec":
        if self.width_range[0] > self.width_range[1] or self.floors_range[0] > self.floors_range[1]:
            raise ValueError("Plages invalides")
        return self


def _deep_set(data: dict[str, Any], dotted: str, value: Any) -> None:
    """``_deep_set(d, "roof.kind", "hip")`` ; les dicts sont fusionnés récursivement."""
    parts = dotted.split(".")
    cur = data
    for p in parts[:-1]:
        if not isinstance(cur.get(p), dict):
            cur[p] = {}
        cur = cur[p]
    last = parts[-1]
    if isinstance(value, dict) and isinstance(cur.get(last), dict):
        for k, v in value.items():
            _deep_set(cur[last], k, v)
    else:
        cur[last] = value


def spec_json_schema() -> dict[str, Any]:
    return BuildingSpec.model_json_schema()
