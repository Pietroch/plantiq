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


def project_on_segment(point: Point, a: Point, b: Point) -> tuple[float, Point]:
    """Closest point of segment [a,b] to `point`, with its parameter t in [0,1]."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    squared = dx * dx + dy * dy
    if squared == 0:
        return 0.0, a
    t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / squared
    t = max(0.0, min(1.0, t))
    return t, (a[0] + t * dx, a[1] + t * dy)


def closest_point_on_outline(point: Point, vertices: list[Point]) -> tuple[float, Point]:
    """Distance to the nearest wall and the point on it. Plan units, not centimetres."""
    best: tuple[float, Point] | None = None
    for a, b in walls(vertices):
        _, projected = project_on_segment(point, a, b)
        distance = math.dist(point, projected)
        if best is None or distance < best[0]:
            best = (distance, projected)
    return best if best else (float("inf"), point)


def point_in_polygon(point: Point, vertices: list[Point], tolerance: float = 0.0) -> bool:
    """Crossing number with the half-open rule.

    Deliberately not built on segments_cross: that one ignores shared endpoints,
    which would miss a ray passing exactly through a vertex — a frequent case
    since vertices snap to the grid and clicks are integers.

    `tolerance` is expressed in plan units, because a room may not be calibrated
    when a plant is placed. It is a guard, never a measurement.
    """
    if len(vertices) < 3:
        return False

    x, y = point
    inside = False
    for a, b in walls(vertices):
        if (a[1] > y) != (b[1] > y):
            crossing_x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x < crossing_x:
                inside = not inside

    if inside or tolerance <= 0:
        return inside
    return closest_point_on_outline(point, vertices)[0] <= tolerance


def pull_inside(point: Point, vertices: list[Point], tolerance: float) -> Point | None:
    """Point unchanged when inside, pulled onto the wall when just outside, None beyond.

    Keeps every stored marker inside its polygon, so nothing downstream ever has
    to qualify a point that sits outside the room.
    """
    if point_in_polygon(point, vertices):
        return point
    distance, projected = closest_point_on_outline(point, vertices)
    return projected if distance <= tolerance else None
