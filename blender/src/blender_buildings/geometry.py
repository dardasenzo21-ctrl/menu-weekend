"""Géométrie 2D pure Python (sans bpy) : aires, périmètres, décalages de polygones."""

from __future__ import annotations

import math
from typing import Sequence

Point = tuple[float, float]


def signed_area(pts: Sequence[Point]) -> float:
    """Aire signée (formule du lacet) : > 0 si anti-horaire."""
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def area(pts: Sequence[Point]) -> float:
    return abs(signed_area(pts))


def perimeter(pts: Sequence[Point]) -> float:
    n = len(pts)
    return sum(math.dist(pts[i], pts[(i + 1) % n]) for i in range(n))


def ensure_ccw(pts: Sequence[Point]) -> list[Point]:
    pts = [(float(x), float(y)) for x, y in pts]
    if signed_area(pts) < 0:
        pts.reverse()
    return pts


def centroid(pts: Sequence[Point]) -> Point:
    a = signed_area(pts)
    if abs(a) < 1e-12:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (sum(xs) / len(pts), sum(ys) / len(pts))
    cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return (cx / (6 * a), cy / (6 * a))


def bbox(pts: Sequence[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def offset_polygon(pts: Sequence[Point], distance: float) -> list[Point]:
    """Décale un polygone anti-horaire de ``distance`` (positif = vers l'extérieur).

    Décalage par intersection des arêtes voisines (onglet). Fiable pour des polygones
    simples et des distances petites devant les arêtes (ce qui est notre cas : corniches,
    acrotères, retraits de toiture).
    """
    pts = ensure_ccw(pts)
    n = len(pts)
    if n < 3:
        return list(pts)
    lines = []
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        # normale extérieure d'une arête anti-horaire : (dy, -dx)
        nx, ny = dy / length, -dx / length
        lines.append(((x1 + nx * distance, y1 + ny * distance), (dx / length, dy / length)))
    m = len(lines)
    out: list[Point] = []
    for i in range(m):
        (p1, d1) = lines[i - 1]
        (p2, d2) = lines[i]
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(cross) < 1e-9:  # arêtes colinéaires
            out.append(p2)
            continue
        # p1 + t*d1 = p2 + s*d2
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / cross
        out.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))
    return out


def is_rectangle(pts: Sequence[Point], tol: float = 1e-6) -> bool:
    if len(pts) != 4:
        return False
    for i in range(4):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        cx, cy = pts[(i + 1) % 4]
        dot = (ax - bx) * (cx - bx) + (ay - by) * (cy - by)
        if abs(dot) > tol * max(1.0, abs(ax - bx) + abs(cx - bx)):
            return False
    return True


def edges(pts: Sequence[Point]) -> list[tuple[Point, Point]]:
    n = len(pts)
    return [(pts[i], pts[(i + 1) % n]) for i in range(n)]


def rotate(pts: Sequence[Point], angle_deg: float) -> list[Point]:
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    return [(x * c - y * s, x * s + y * c) for x, y in pts]


def translate(pts: Sequence[Point], dx: float, dy: float) -> list[Point]:
    return [(x + dx, y + dy) for x, y in pts]
