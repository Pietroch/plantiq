# app/src/plantiq/engine/geometry.py

import math

Point = tuple[float, float]


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def segments_cross(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """True when [p1,p2] and [p3,p4] properly cross. Shared endpoints don't count."""
    d1 = _cross(p3, p4, p1)
    d2 = _cross(p3, p4, p2)
    d3 = _cross(p1, p2, p3)
    d4 = _cross(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def walls(vertices: list[Point]) -> list[tuple[Point, Point]]:
    """Wall i runs from vertex i to vertex i+1, the last one closing the polygon."""
    count = len(vertices)
    return [(vertices[i], vertices[(i + 1) % count]) for i in range(count)]


def is_simple(vertices: list[Point]) -> bool:
    """False when the outline crosses itself — a bow tie the shoelace formula can't measure."""
    edges = walls(vertices)
    count = len(edges)
    if count < 4:
        return count == 3
    for i in range(count):
        for j in range(i + 1, count):
            # Adjacent walls legitimately share a vertex
            if j == i + 1 or (i == 0 and j == count - 1):
                continue
            if segments_cross(*edges[i], *edges[j]):
                return False
    return True


def polygon_area(vertices: list[Point]) -> float:
    """Shoelace formula. Meaningless on a self-crossing outline — check is_simple first."""
    total = 0.0
    for a, b in walls(vertices):
        total += a[0] * b[1] - b[0] * a[1]
    return abs(total) / 2


def wall_lengths(vertices: list[Point]) -> list[float]:
    return [math.dist(a, b) for a, b in walls(vertices)]
