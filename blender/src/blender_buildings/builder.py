"""Génération du maillage d'un bâtiment à partir d'une ``BuildingSpec``. Nécessite ``bpy``.

Principe : chaque façade est découpée en travées ; chaque travée est un ensemble de
quadrilatères (allège, linteau, trumeaux, embrasures, cadre, vitrage). Les corniches,
acrotères, balcons, lucarnes et toitures sont des prismes explicites. Aucune opération
booléenne : la génération est déterministe, rapide et exportable proprement.
"""

from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass, field
from typing import Any, Sequence

import bpy

from . import geometry
from .materials import assign_materials
from .metrics import compute_metrics
from .spec import BlockSpec, BuildingSpec, StreetSpec
from .presets import get_preset

Vec3 = tuple[float, float, float]
Point = tuple[float, float]


# ----------------------------------------------------------------------------------------------
# Accumulateur de maillage
# ----------------------------------------------------------------------------------------------
@dataclass
class MeshBuilder:
    verts: list[Vec3] = field(default_factory=list)
    faces: list[list[int]] = field(default_factory=list)
    face_mats: list[int] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    _index: dict[tuple[int, int, int], int] = field(default_factory=dict)

    def mat(self, name: str) -> int:
        if name not in self.materials:
            self.materials.append(name)
        return self.materials.index(name)

    def vert(self, p: Vec3) -> int:
        key = (round(p[0] * 10000), round(p[1] * 10000), round(p[2] * 10000))
        idx = self._index.get(key)
        if idx is None:
            idx = len(self.verts)
            self.verts.append((float(p[0]), float(p[1]), float(p[2])))
            self._index[key] = idx
        return idx

    def face(self, pts: Sequence[Vec3], material: str) -> None:
        idx: list[int] = []
        for p in pts:
            i = self.vert(p)
            if not idx or idx[-1] != i:
                idx.append(i)
        if len(idx) > 2 and idx[0] == idx[-1]:
            idx.pop()
        if len(idx) < 3:
            return
        self.faces.append(idx)
        self.face_mats.append(self.mat(material))

    # --- primitives orientées (normales sortantes) ---------------------------------------------
    def polygon_cap(self, pts: Sequence[Point], z: float, material: str, up: bool = True) -> None:
        ring = [(x, y, z) for x, y in pts]
        self.face(ring if up else list(reversed(ring)), material)

    def ring_prism(
        self,
        outer: Sequence[Point],
        inner: Sequence[Point],
        z0: float,
        z1: float,
        material: str,
        top: bool = True,
        bottom: bool = True,
        outer_walls: bool = True,
        inner_walls: bool = True,
        top_material: str | None = None,
    ) -> None:
        """Anneau prismatique entre deux polygones de même nombre de sommets."""
        n = len(outer)
        assert len(inner) == n, "ring_prism : polygones de tailles différentes"
        tm = top_material or material
        for i in range(n):
            o0, o1 = outer[i], outer[(i + 1) % n]
            i0, i1 = inner[i], inner[(i + 1) % n]
            if outer_walls:
                self.face([(*o0, z0), (*o1, z0), (*o1, z1), (*o0, z1)], material)
            if inner_walls:
                self.face([(*i1, z0), (*i0, z0), (*i0, z1), (*i1, z1)], material)
            if top:
                self.face([(*o0, z1), (*o1, z1), (*i1, z1), (*i0, z1)], tm)
            if bottom:
                self.face([(*i0, z0), (*i1, z0), (*o1, z0), (*o0, z0)], material)

    def hexahedron(self, bottom: Sequence[Vec3], top: Sequence[Vec3], material: str, faces: Sequence[str] = ("bottom", "top", "sides")) -> None:
        """Prisme à base quadrangulaire. ``bottom`` anti-horaire vu de dessus."""
        if "bottom" in faces:
            self.face(list(reversed(list(bottom))), material)
        if "top" in faces:
            self.face(list(top), material)
        if "sides" in faces:
            for i in range(4):
                self.face([bottom[i], bottom[(i + 1) % 4], top[(i + 1) % 4], top[i]], material)

    def slope_ring(self, lower: Sequence[Point], z0: float, upper: Sequence[Point], z1: float, material: str) -> None:
        """Pans de toiture entre un polygone bas et un polygone haut (même nombre de sommets)."""
        n = len(lower)
        for i in range(n):
            l0, l1 = lower[i], lower[(i + 1) % n]
            u0, u1 = upper[i], upper[(i + 1) % n]
            self.face([(*l0, z0), (*l1, z0), (*u1, z1), (*u0, z1)], material)

    def to_object(self, name: str, collection: Any | None = None, library_materials: bool = True) -> Any:
        """Crée l'objet. ``library_materials=False`` : les noms désignent des matériaux de la scène (créés vides s'ils manquent)."""
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.verts, [], self.faces)
        mesh.validate(verbose=False)
        obj = bpy.data.objects.new(name, mesh)
        # Les slots doivent exister AVANT d'écrire material_index (materials.clear() remet les index à 0).
        if library_materials:
            assign_materials(obj, self.materials)
        else:
            for n in self.materials:
                obj.data.materials.append(bpy.data.materials.get(n) or bpy.data.materials.new(n))
        if len(mesh.polygons) == len(self.face_mats):
            mesh.polygons.foreach_set("material_index", self.face_mats)
        else:  # validate() a pu retirer des faces dégénérées
            for poly, mi in zip(mesh.polygons, self.face_mats):
                poly.material_index = mi
        _box_uvs(mesh)
        mesh.update()
        (collection or bpy.context.scene.collection).objects.link(obj)
        return obj


def _box_uvs(mesh: Any) -> None:
    uv = mesh.uv_layers.new(name="UVMap")
    data = uv.data
    for poly in mesh.polygons:
        nx, ny, nz = (abs(c) for c in poly.normal)
        for li in poly.loop_indices:
            x, y, z = mesh.vertices[mesh.loops[li].vertex_index].co
            if nz >= nx and nz >= ny:
                data[li].uv = (x, y)
            elif nx >= ny:
                data[li].uv = (y, z)
            else:
                data[li].uv = (x, z)


# ----------------------------------------------------------------------------------------------
# Repère local d'une façade
# ----------------------------------------------------------------------------------------------
@dataclass
class WallFrame:
    a: Point
    b: Point

    def __post_init__(self) -> None:
        dx, dy = self.b[0] - self.a[0], self.b[1] - self.a[1]
        self.length = math.hypot(dx, dy)
        self.t = (dx / self.length, dy / self.length)
        self.n = (self.t[1], -self.t[0])  # normale extérieure (polygone anti-horaire)

    def p(self, u: float, z: float, out: float = 0.0) -> Vec3:
        """Point à ``u`` le long du mur, ``z`` vertical, ``out`` vers l'extérieur (négatif = retrait)."""
        return (
            self.a[0] + self.t[0] * u + self.n[0] * out,
            self.a[1] + self.t[1] * u + self.n[1] * out,
            z,
        )

    def bays(self, bay_width: float) -> list[tuple[float, float]]:
        n = max(1, round(self.length / bay_width))
        w = self.length / n
        return [(i * w, (i + 1) * w) for i in range(n)]


# ----------------------------------------------------------------------------------------------
# Façades
# ----------------------------------------------------------------------------------------------
def _window_rect(spec: BuildingSpec, storey: int, bay: tuple[float, float], z0: float, z1: float) -> tuple[float, float, float, float] | None:
    """Rectangle (u0, u1, zw0, zw1) de la baie d'une travée, ou None si trumeau plein."""
    ub0, ub1 = bay
    bw = ub1 - ub0
    w = spec.windows
    gf = spec.ground_floor
    if storey == 0 and gf.storefront:
        gw = bw * gf.glazing_ratio
        if gw < 0.3:
            return None
        c = (ub0 + ub1) / 2
        return (c - gw / 2, c + gw / 2, z0 + 0.15, z1 - 0.7)
    style = w.style
    if style == "none":
        return None
    if style == "punched":
        if w.width >= bw - 0.2:
            width = max(0.3, bw - 0.4)
        else:
            width = w.width
        c = (ub0 + ub1) / 2
        zw0 = z0 + w.sill
        zw1 = min(zw0 + w.height, z1 - 0.2)
        return (c - width / 2, c + width / 2, zw0, zw1)
    if style == "ribbon":
        zw0 = z0 + w.sill
        zw1 = min(zw0 + w.height, z1 - 0.2)
        return (ub0 + w.mullion / 2, ub1 - w.mullion / 2, zw0, zw1)
    if style == "curtain":
        return (ub0 + w.mullion / 2, ub1 - w.mullion / 2, z0 + w.spandrel, z1 - 0.15)
    return None


def _build_bay(mb: MeshBuilder, fr: WallFrame, spec: BuildingSpec, storey: int, bay: tuple[float, float], z0: float, z1: float, wall_mat: str, base_h: float, base_mat: str | None) -> None:
    ub0, ub1 = bay
    rect = _window_rect(spec, storey, bay, z0, z1)

    def band(u0: float, u1: float, za: float, zb: float, mat: str) -> None:
        if zb - za <= 1e-6 or u1 - u0 <= 1e-6:
            return
        mb.face([fr.p(u0, za), fr.p(u1, za), fr.p(u1, zb), fr.p(u0, zb)], mat)

    def band_with_base(u0: float, u1: float, za: float, zb: float) -> None:
        if storey == 0 and base_mat and base_h > za:
            split = min(base_h, zb)
            band(u0, u1, za, split, base_mat)
            band(u0, u1, split, zb, wall_mat)
        else:
            band(u0, u1, za, zb, wall_mat)

    if rect is None or rect[1] - rect[0] <= 0.05 or rect[3] - rect[2] <= 0.05:
        band_with_base(ub0, ub1, z0, z1)
        return
    u0, u1, zw0, zw1 = rect
    band_with_base(ub0, ub1, z0, zw0)  # allège
    band(ub0, ub1, zw1, z1, wall_mat)  # linteau
    band_with_base(ub0, u0, zw0, zw1)  # trumeau gauche
    band_with_base(u1, ub1, zw0, zw1)  # trumeau droit

    w = spec.windows
    r = w.recess if not (storey == 0 and spec.ground_floor.storefront) else min(w.recess, 0.2)
    f = w.frame
    frame_mat = w.frame_material
    glass_mat = w.glass_material
    if r > 1e-4:
        # embrasures (normales vers l'intérieur de l'ouverture)
        mb.face([fr.p(u0, zw0, -r), fr.p(u1, zw0, -r), fr.p(u1, zw0), fr.p(u0, zw0)], wall_mat)  # appui
        mb.face([fr.p(u0, zw1), fr.p(u1, zw1), fr.p(u1, zw1, -r), fr.p(u0, zw1, -r)], wall_mat)  # linteau
        mb.face([fr.p(u0, zw0), fr.p(u0, zw1), fr.p(u0, zw1, -r), fr.p(u0, zw0, -r)], wall_mat)  # tableau gauche
        mb.face([fr.p(u1, zw0, -r), fr.p(u1, zw1, -r), fr.p(u1, zw1), fr.p(u1, zw0)], wall_mat)  # tableau droit
    if f > 1e-4 and (u1 - u0) > 2 * f + 0.05 and (zw1 - zw0) > 2 * f + 0.05:
        gi = (u0 + f, u1 - f, zw0 + f, zw1 - f)
        # cadre : 4 bandes
        mb.face([fr.p(u0, zw0, -r), fr.p(u1, zw0, -r), fr.p(gi[1], gi[2], -r), fr.p(gi[0], gi[2], -r)], frame_mat)
        mb.face([fr.p(gi[0], gi[3], -r), fr.p(gi[1], gi[3], -r), fr.p(u1, zw1, -r), fr.p(u0, zw1, -r)], frame_mat)
        mb.face([fr.p(u0, zw0, -r), fr.p(gi[0], gi[2], -r), fr.p(gi[0], gi[3], -r), fr.p(u0, zw1, -r)], frame_mat)
        mb.face([fr.p(gi[1], gi[2], -r), fr.p(u1, zw0, -r), fr.p(u1, zw1, -r), fr.p(gi[1], gi[3], -r)], frame_mat)
        mb.face([fr.p(gi[0], gi[2], -r - 0.02), fr.p(gi[1], gi[2], -r - 0.02), fr.p(gi[1], gi[3], -r - 0.02), fr.p(gi[0], gi[3], -r - 0.02)], glass_mat)
    else:
        mb.face([fr.p(u0, zw0, -r), fr.p(u1, zw0, -r), fr.p(u1, zw1, -r), fr.p(u0, zw1, -r)], glass_mat)


def _build_balcony(mb: MeshBuilder, fr: WallFrame, spec: BuildingSpec, storey: int, bays: list[tuple[float, float]], z: float) -> None:
    b = spec.balconies
    z0 = spec.floor_levels()[storey]
    spans: list[tuple[float, float]]
    if b.continuous:
        spans = [(0.25, fr.length - 0.25)]
    else:
        spans = []
        for bay in bays:
            rect = _window_rect(spec, storey, bay, z0, z0 + spec.floor_height)
            if rect is None:
                continue
            c = (rect[0] + rect[1]) / 2
            half = (rect[1] - rect[0]) / 2 + 0.4
            spans.append((max(0.1, c - half), min(fr.length - 0.1, c + half)))
    for (u0, u1) in spans:
        if u1 - u0 < 0.5:
            continue
        # dalle
        mb.hexahedron(
            [fr.p(u0, z - b.slab_thickness, 0.0), fr.p(u1, z - b.slab_thickness, 0.0), fr.p(u1, z - b.slab_thickness, b.depth), fr.p(u0, z - b.slab_thickness, b.depth)],
            [fr.p(u0, z, 0.0), fr.p(u1, z, 0.0), fr.p(u1, z, b.depth), fr.p(u0, z, b.depth)],
            b.material,
        )
        # garde-corps : plaque avant + 2 retours
        t = 0.05
        rh = b.railing_height
        for (a0, a1, o0, o1) in (
            (u0, u1, b.depth - t, b.depth),
            (u0, u0 + t, 0.0, b.depth - t),
            (u1 - t, u1, 0.0, b.depth - t),
        ):
            mb.hexahedron(
                [fr.p(a0, z, o0), fr.p(a1, z, o0), fr.p(a1, z, o1), fr.p(a0, z, o1)],
                [fr.p(a0, z + rh, o0), fr.p(a1, z + rh, o0), fr.p(a1, z + rh, o1), fr.p(a0, z + rh, o1)],
                b.railing_material,
                faces=("top", "sides"),
            )


def _build_dormers(mb: MeshBuilder, fr: WallFrame, spec: BuildingSpec, wall_h: float) -> None:
    r = spec.roof
    w = spec.windows
    dw, dh, dd = 1.2, 1.7, min(r.mansard_inset * 0.95, 2.0)
    for (ub0, ub1) in fr.bays(w.bay_width):
        c = (ub0 + ub1) / 2
        if ub1 - ub0 < dw + 0.4:
            continue
        u0, u1 = c - dw / 2, c + dw / 2
        z0, z1 = wall_h + 0.25, wall_h + 0.25 + dh
        front, back = -0.35, -dd
        mb.hexahedron(
            [fr.p(u0, z0, back), fr.p(u1, z0, back), fr.p(u1, z0, front), fr.p(u0, z0, front)],
            [fr.p(u0, z1, back), fr.p(u1, z1, back), fr.p(u1, z1, front), fr.p(u0, z1, front)],
            r.material,
            faces=("top", "sides"),
        )
        g = 0.12
        mb.face(
            [fr.p(u0 + g, z0 + g, front + 0.01), fr.p(u1 - g, z0 + g, front + 0.01), fr.p(u1 - g, z1 - g, front + 0.01), fr.p(u0 + g, z1 - g, front + 0.01)],
            w.glass_material,
        )


def _build_pilasters(mb: MeshBuilder, fr: WallFrame, spec: BuildingSpec, bays: list[tuple[float, float]]) -> None:
    h = spec.ground_floor.height
    mat = spec.facade.trim_material
    for i in range(1, len(bays)):
        u = bays[i][0]
        mb.hexahedron(
            [fr.p(u - 0.2, 0, 0), fr.p(u + 0.2, 0, 0), fr.p(u + 0.2, 0, 0.15), fr.p(u - 0.2, 0, 0.15)],
            [fr.p(u - 0.2, h, 0), fr.p(u + 0.2, h, 0), fr.p(u + 0.2, h, 0.15), fr.p(u - 0.2, h, 0.15)],
            mat,
            faces=("top", "sides"),
        )


# ----------------------------------------------------------------------------------------------
# Toitures
# ----------------------------------------------------------------------------------------------
def _safe_inset(pts: Sequence[Point], wanted: float) -> float:
    x0, y0, x1, y1 = geometry.bbox(pts)
    limit = min(x1 - x0, y1 - y0) / 2 - 0.3
    return max(0.1, min(wanted, limit))


def _build_roof(mb: MeshBuilder, spec: BuildingSpec, pts: list[Point], wall_h: float) -> None:
    r = spec.roof
    mat = r.material
    trim = spec.facade.trim_material
    kind = r.kind
    if kind == "gable" and not (spec.footprint.kind == "rect"):
        kind = "hip"

    if kind == "flat":
        mb.polygon_cap(pts, wall_h, mat)
        return

    if kind == "parapet":
        inner = geometry.offset_polygon(pts, -r.parapet_thickness)
        top = wall_h + r.parapet_height
        mb.ring_prism(pts, inner, wall_h, top, trim, top=True, bottom=False, outer_walls=True, inner_walls=True)
        mb.polygon_cap(inner, wall_h, mat)
        return

    if kind == "hip":
        eave = geometry.offset_polygon(pts, r.overhang) if r.overhang > 0 else list(pts)
        if r.overhang > 0:
            mb.ring_prism(eave, pts, wall_h - 0.12, wall_h, trim, top=False, bottom=True, outer_walls=True, inner_walls=False)
        if spec.footprint.kind == "rect":
            # faîtage le long du grand axe
            x0, y0, x1, y1 = geometry.bbox(eave)
            L, W = x1 - x0, y1 - y0
            z1 = wall_h + r.height
            if L >= W:
                half = max(0.0, (L - W) / 2)
                r1, r2 = (-half, 0.0, z1), (half, 0.0, z1)
                e = [(x0, y0, wall_h), (x1, y0, wall_h), (x1, y1, wall_h), (x0, y1, wall_h)]
                mb.face([e[0], e[1], r2, r1], mat)
                mb.face([e[2], e[3], r1, r2], mat)
                mb.face([e[1], e[2], r2], mat)
                mb.face([e[3], e[0], r1], mat)
            else:
                half = max(0.0, (W - L) / 2)
                r1, r2 = (0.0, -half, z1), (0.0, half, z1)
                e = [(x0, y0, wall_h), (x1, y0, wall_h), (x1, y1, wall_h), (x0, y1, wall_h)]
                mb.face([e[1], e[2], r2, r1], mat)
                mb.face([e[3], e[0], r1, r2], mat)
                mb.face([e[0], e[1], r1], mat)
                mb.face([e[2], e[3], r2], mat)
            return
        inset = _safe_inset(eave, 0.35 * min(geometry.bbox(eave)[2] - geometry.bbox(eave)[0], geometry.bbox(eave)[3] - geometry.bbox(eave)[1]))
        top_poly = geometry.offset_polygon(eave, -inset)
        mb.slope_ring(eave, wall_h, top_poly, wall_h + r.height, mat)
        mb.polygon_cap(top_poly, wall_h + r.height, mat)
        return

    if kind == "gable":
        x0, y0, x1, y1 = geometry.bbox(pts)
        L, W = x1 - x0, y1 - y0
        z1 = wall_h + r.height
        o = r.overhang
        if L >= W:
            e = [(x0, y0 - o, wall_h), (x1, y0 - o, wall_h), (x1, y1 + o, wall_h), (x0, y1 + o, wall_h)]
            r1, r2 = (x0, (y0 + y1) / 2, z1), (x1, (y0 + y1) / 2, z1)
            mb.face([e[0], e[1], r2, r1], mat)
            mb.face([e[2], e[3], r1, r2], mat)
            mb.face([e[1], e[2], r2], spec.facade.material)  # pignon est
            mb.face([e[3], e[0], r1], spec.facade.material)  # pignon ouest
            if o > 0:
                mb.face([(x0, y0 - o, wall_h), (x0, y0, wall_h), (x1, y0, wall_h), (x1, y0 - o, wall_h)], trim)
                mb.face([(x1, y1 + o, wall_h), (x1, y1, wall_h), (x0, y1, wall_h), (x0, y1 + o, wall_h)], trim)
        else:
            e = [(x0 - o, y0, wall_h), (x1 + o, y0, wall_h), (x1 + o, y1, wall_h), (x0 - o, y1, wall_h)]
            r1, r2 = ((x0 + x1) / 2, y0, z1), ((x0 + x1) / 2, y1, z1)
            mb.face([e[1], e[2], r2, r1], mat)
            mb.face([e[3], e[0], r1, r2], mat)
            mb.face([e[0], e[1], r1], spec.facade.material)
            mb.face([e[2], e[3], r2], spec.facade.material)
            if o > 0:
                mb.face([(x1 + o, y0, wall_h), (x1, y0, wall_h), (x1, y1, wall_h), (x1 + o, y1, wall_h)], trim)
                mb.face([(x0 - o, y1, wall_h), (x0, y1, wall_h), (x0, y0, wall_h), (x0 - o, y0, wall_h)], trim)
        return

    if kind == "mansard":
        inset = _safe_inset(pts, r.mansard_inset)
        brisis_top = geometry.offset_polygon(pts, -inset)
        z_b = wall_h + r.mansard_height
        mb.slope_ring(pts, wall_h, brisis_top, z_b, mat)
        if r.height > 0.05:
            inset2 = _safe_inset(pts, inset + 0.3 * (min(geometry.bbox(pts)[2] - geometry.bbox(pts)[0], geometry.bbox(pts)[3] - geometry.bbox(pts)[1]) / 2 - inset))
            top_poly = geometry.offset_polygon(pts, -inset2)
            mb.slope_ring(brisis_top, z_b, top_poly, z_b + r.height, mat)
            mb.polygon_cap(top_poly, z_b + r.height, mat)
        else:
            mb.polygon_cap(brisis_top, z_b, mat)
        if r.dormers:
            for (a, b) in geometry.edges(pts):
                _build_dormers(mb, WallFrame(a, b), spec, wall_h)
        return

    raise ValueError(f"Toiture inconnue : {kind}")


# ----------------------------------------------------------------------------------------------
# Bâtiment complet
# ----------------------------------------------------------------------------------------------
def _cornice_levels(spec: BuildingSpec) -> list[float]:
    fc = spec.facade
    if not fc.cornices:
        return []
    levels = spec.floor_levels()
    wall_h = spec.wall_height()
    if fc.cornice_floors == "all":
        idx = list(range(1, spec.floors + 1))
    elif fc.cornice_floors == "top":
        idx = [spec.floors]
    else:
        idx = list(fc.cornice_floors)
    out = []
    for f in idx:
        out.append(wall_h if f >= spec.floors else levels[f])
    return sorted(set(out))


def build_building_mesh(spec: BuildingSpec) -> MeshBuilder:
    """Construit le maillage (repère local : origine au centre de l'emprise, Z=0 au sol)."""
    mb = MeshBuilder()
    pts = spec.footprint.polygon()
    levels = spec.floor_levels()
    wall_h = spec.wall_height()
    fc = spec.facade
    frames = [WallFrame(a, b) for (a, b) in geometry.edges(pts)]

    # sol du bâtiment
    mb.polygon_cap(pts, 0.0, fc.material, up=False)

    for storey in range(spec.floors):
        z0 = levels[storey]
        z1 = levels[storey + 1] if storey + 1 < spec.floors else wall_h
        wall_mat = (spec.ground_floor.material or fc.material) if storey == 0 else fc.material
        for fr in frames:
            bays = fr.bays(spec.windows.bay_width)
            for bay in bays:
                _build_bay(mb, fr, spec, storey, bay, z0, z1, wall_mat, fc.base_height, fc.base_material)
            if storey in spec.balconies.floors:
                _build_balcony(mb, fr, spec, storey, bays, z0)
            if storey == 0 and fc.pilasters:
                _build_pilasters(mb, fr, spec, bays)

    for z in _cornice_levels(spec):
        outer = geometry.offset_polygon(pts, fc.cornice_depth)
        mb.ring_prism(outer, pts, z - fc.cornice_height, z, fc.trim_material, top=True, bottom=True, outer_walls=True, inner_walls=False)

    _build_roof(mb, spec, pts, wall_h)
    return mb


def build_building(spec: BuildingSpec | dict[str, Any], collection: Any | None = None, with_site: bool = True) -> dict[str, Any]:
    """Construit le bâtiment dans la scène courante. Retourne un résumé (objet, stats, métriques)."""
    if not isinstance(spec, BuildingSpec):
        spec = BuildingSpec.model_validate(spec)
    mb = build_building_mesh(spec)
    coll = collection
    if coll is None:
        coll = bpy.data.collections.get("Buildings")
        if coll is None:
            coll = bpy.data.collections.new("Buildings")
            bpy.context.scene.collection.children.link(coll)
    obj = mb.to_object(spec.name, coll)
    obj.location = spec.position
    obj.rotation_euler = (0.0, 0.0, math.radians(spec.rotation_deg))
    obj["bb_spec"] = spec.model_dump_json()
    obj["bb_use"] = spec.use
    if with_site and spec.site.ground:
        from .scene import ensure_ground

        ensure_ground(spec.site.ground_size, spec.site.ground_material)
    metrics = compute_metrics(spec)
    return {
        "object": obj.name,
        "collection": coll.name,
        "vertices": len(mb.verts),
        "faces": len(mb.faces),
        "materials": list(mb.materials),
        "height_m": round(spec.total_height(), 2),
        "metrics": metrics,
    }


def build_block(block: BlockSpec | dict[str, Any]) -> dict[str, Any]:
    if not isinstance(block, BlockSpec):
        block = BlockSpec.model_validate(block)
    coll = bpy.data.collections.new(block.name)
    bpy.context.scene.collection.children.link(coll)
    results = [build_building(b, collection=coll, with_site=False) for b in block.buildings]
    if block.site.ground:
        from .scene import ensure_ground

        ensure_ground(block.site.ground_size, block.site.ground_material)
    return {
        "collection": coll.name,
        "buildings": results,
        "total_gross_floor_area_m2": round(sum(r["metrics"]["gross_floor_area_m2"] for r in results), 1),
        "total_footprint_m2": round(sum(r["metrics"]["footprint_area_m2"] for r in results), 1),
    }


def generate_street(street: StreetSpec | dict[str, Any]) -> BlockSpec:
    """Génère les specs d'une rue (sans construire) : bâtiments alignés sur l'axe X, façades au sud."""
    if not isinstance(street, StreetSpec):
        street = StreetSpec.model_validate(street)
    rng = random.Random(street.seed)
    base = get_preset(street.preset, street.overrides)
    buildings: list[BuildingSpec] = []
    x = 0.0
    widths = [rng.uniform(*street.width_range) for _ in range(street.count)]
    total = sum(widths) + street.gap * (street.count - 1)
    x = -total / 2
    for i, w in enumerate(widths):
        floors = rng.randint(*street.floors_range)
        data = base.model_dump()
        data["name"] = f"{base.name} {i + 1}"
        data["floors"] = floors
        data["seed"] = street.seed * 1000 + i
        if data["footprint"]["kind"] in ("rect", "L", "U"):
            data["footprint"]["width"] = round(w, 2)
            if data["footprint"]["kind"] in ("L", "U"):
                data["footprint"]["wing_width"] = min(data["footprint"]["wing_width"], w * 0.45)
        data["position"] = (x + w / 2, 0.0, 0.0)
        data["balconies"]["floors"] = [f for f in data["balconies"]["floors"] if f < floors]
        if isinstance(data["facade"]["cornice_floors"], list):
            data["facade"]["cornice_floors"] = [f for f in data["facade"]["cornice_floors"] if f <= floors]
        data["site"] = {"ground": False}
        buildings.append(BuildingSpec.model_validate(data))
        x += w + street.gap
    return BlockSpec(name=street.name, buildings=buildings, site=street.site)


def build_street(street: StreetSpec | dict[str, Any]) -> dict[str, Any]:
    return build_block(generate_street(street))


def build_site(site: "SiteModel | dict[str, Any]", context: bool = True, ground: bool = True) -> dict[str, Any]:
    """Construit un site réel (``geo.site_from_address``) : cible détaillée, voisins en massing, orthophoto au sol."""
    from .geo import SiteModel

    if not isinstance(site, SiteModel):
        site = SiteModel.model_validate(site)
    coll = bpy.data.collections.new("Site " + site.address[:40])
    bpy.context.scene.collection.children.link(coll)
    target = build_building(site.target, collection=coll, with_site=False)
    ctx_results = []
    if context:
        ctx_coll = bpy.data.collections.new("Context")
        coll.children.link(ctx_coll)
        for spec in site.context:
            try:
                ctx_results.append(build_building(spec, collection=ctx_coll, with_site=False))
            except Exception as exc:  # noqa: BLE001 — un voisin mal formé ne doit pas bloquer le site
                ctx_results.append({"object": None, "error": f"{spec.name}: {exc}"})
    ground_info: dict[str, Any] | None = None
    if ground:
        from .scene import ensure_ground, ensure_textured_ground

        if site.ortho and os.path.exists(site.ortho.path):
            ensure_textured_ground(site.ortho.half_size_m, site.ortho.path)
            ground_info = {"textured": True, "image": site.ortho.path, "half_size_m": site.ortho.half_size_m}
        else:
            ensure_ground(max(200.0, 4 * max(abs(c) for c in site.target.position[:2]) + 100), "asphalt")
            ground_info = {"textured": False}
    return {
        "address": site.address,
        "label": site.label,
        "lat": site.lat,
        "lon": site.lon,
        "collection": coll.name,
        "target": target,
        "context_count": sum(1 for r in ctx_results if r.get("object")),
        "context_errors": [r["error"] for r in ctx_results if r.get("error")],
        "ground": ground_info,
        "facade_azimuth_deg": site.facade_azimuth_deg,
        "street_distance_m": site.street_distance_m,
        "parcel": {k: v for k, v in (site.parcel or {}).items() if k != "ring"} or None,
        "sources": site.sources,
        "notes": site.notes,
    }
