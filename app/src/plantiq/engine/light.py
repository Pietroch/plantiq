# app/src/plantiq/engine/light.py

import math
from dataclasses import dataclass
from enum import IntEnum

from plantiq.engine.geometry import (
    Point,
    point_in_polygon,
    project_on_segment,
    segments_cross,
    walls,
)

# Azimuth weights: how much light a window of that orientation brings
AZIMUTH_WEIGHTS = {
    "N": 0.30,
    "NE": 0.45,
    "E": 0.70,
    "SE": 0.85,
    "S": 1.00,
    "SO": 0.85,
    "O": 0.70,
    "NO": 0.45,
}
CARDINALS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]

# north_angle convention, shared by the schema, this module and the editor:
# degrees turning clockwise from the top of the drawing to true north, so 0
# means north is up. The top of the plan therefore heads (360 - north_angle),
# which is what rooms/editor.html reads out. Nothing stores the convention —
# test_light.py pins it on the real geometry of the Séjour instead.
NORTH_ANGLE_UP_IS_ZERO = 0.0

# Reference opening: a three-metre window scores its full azimuth weight.
# A narrow one lets in proportionally less, a bay window more.
REFERENCE_WIDTH_M = 3.0

# An overcast sky dims the same window: a fully covered one keeps 40 % of what
# a clear one delivers. The sky modulates the light, never the water directly —
# which is why this multiplies the intensity instead of adding a factor.
CLOUD_ATTENUATION = 0.6


class ExposureLevel(IntEnum):
    """Light levels, ranked. The rank mirrors the declaration order of the
    light_exposure enum in the schema, and it is what turns "is the measured
    level between the species' minimum and maximum" into a comparison.

    Sole owner of the ordering: engine and web both read it from here.
    """

    low = 1
    indirect = 2
    bright_indirect = 3
    direct = 4


# Light falls off fast with distance, normalised to 1 at one metre
EXPOSURE_LEVELS = [
    (1.5, ExposureLevel.direct),
    (0.6, ExposureLevel.bright_indirect),
    (0.2, ExposureLevel.indirect),
]


@dataclass
class Exposure:
    """Two outputs on purpose: a continuous factor for watering, a level for alerts."""

    intensity: float
    level: str
    distance_m: float | None = None
    width_m: float | None = None
    cardinal: str | None = None
    visible: bool = False


def cardinal_of(azimuth: float) -> str:
    return CARDINALS[round((azimuth % 360) / 45) % 8]


def wall_azimuth(vertices: list[Point], wall_index: int, north_angle: float) -> float:
    """Compass bearing the wall faces, in degrees from north.

    The outward side is found by stepping off the wall and testing the polygon,
    which works whatever the winding order of the vertices.

    north_angle follows the convention above: clockwise from the top of the
    drawing to true north. With north at 276°, a wall facing up the plan reads
    84°, that is east.
    """
    a, b = walls(vertices)[wall_index]
    middle = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    normal = (-dy / length, dx / length)

    probe = (middle[0] + normal[0], middle[1] + normal[1])
    if point_in_polygon(probe, vertices):
        normal = (-normal[0], -normal[1])

    # Plan angle, clockwise from the top of the drawing, then referred to north
    plan_angle = math.degrees(math.atan2(normal[0], -normal[1]))
    return (plan_angle - north_angle) % 360


def is_visible(
    point: Point, target: Point, vertices: list[Point], ignore_wall: int | None = None
) -> bool:
    """False when a wall stands between the two — the L-shaped room case.

    ignore_wall skips the wall the target sits in: a window is not hidden by
    the very wall that holds it, though the ray does graze it.
    """
    for index, (a, b) in enumerate(walls(vertices)):
        if index == ignore_wall:
            continue
        if segments_cross(point, target, a, b):
            return False
    return True


def _element_segment(vertices: list[Point], element: dict) -> tuple[Point, Point]:
    a, b = walls(vertices)[element["wall_index"]]
    dx, dy = b[0] - a[0], b[1] - a[1]
    start = (a[0] + element["t_start"] * dx, a[1] + element["t_start"] * dy)
    end = (a[0] + element["t_end"] * dx, a[1] + element["t_end"] * dy)
    return start, end


def element_width(
    vertices: list[Point], element: dict, units_per_cm: float | None
) -> float | None:
    """How wide the opening is, in metres, from its span along the wall."""
    if not units_per_cm:
        return None
    start, end = _element_segment(vertices, element)
    return math.dist(start, end) / units_per_cm / 100


def distance_to_element(
    point: Point, vertices: list[Point], element: dict, units_per_cm: float | None
) -> tuple[float | None, Point]:
    """Distance in metres to the nearest point of the element, and that point."""
    start, end = _element_segment(vertices, element)
    _, closest = project_on_segment(point, start, end)
    units = math.dist(point, closest)
    if not units_per_cm:
        return None, closest
    return units / units_per_cm / 100, closest


def nearest_of_type(
    point: Point,
    vertices: list[Point],
    elements: list[dict],
    kind: str,
    units_per_cm: float | None,
    north_angle: float = 0.0,
) -> dict | None:
    """Closest visible element of that type. Invisible ones are ignored, not scored."""
    best = None
    for element in elements:
        if element["type"] != kind:
            continue
        distance, closest = distance_to_element(point, vertices, element, units_per_cm)
        visible = is_visible(point, closest, vertices, ignore_wall=element["wall_index"])
        candidate = {
            "wall_index": element["wall_index"],
            "distance_m": distance,
            "width_m": element_width(vertices, element, units_per_cm),
            "visible": visible,
            "azimuth": wall_azimuth(vertices, element["wall_index"], north_angle),
        }
        candidate["cardinal"] = cardinal_of(candidate["azimuth"])
        if not visible:
            continue
        if best is None or (distance is not None and distance < (best["distance_m"] or 1e9)):
            best = candidate
    return best


def exposure(
    point: Point,
    vertices: list[Point],
    elements: list[dict],
    north_angle: float,
    units_per_cm: float | None,
) -> Exposure:
    """Light reaching the plant, as a continuous intensity and a level.

    No window, none visible, or no calibration to convert units into metres:
    the answer is 'low' with zero intensity. Missing data degrades, never raises.
    """
    window = nearest_of_type(point, vertices, elements, "window", units_per_cm, north_angle)
    if window is None or window["distance_m"] is None:
        return Exposure(intensity=0.0, level=ExposureLevel.low.name)

    weight = AZIMUTH_WEIGHTS[window["cardinal"]]
    # A wide opening gathers more sky than a narrow one at the same distance
    width_ratio = (window["width_m"] or REFERENCE_WIDTH_M) / REFERENCE_WIDTH_M
    intensity = weight * 4 * width_ratio / (1 + window["distance_m"]) ** 2

    level = ExposureLevel.low
    for threshold, candidate in EXPOSURE_LEVELS:
        if intensity >= threshold:
            level = candidate
            break

    return Exposure(
        intensity=intensity,
        # The name, not the rank: it is what the schema stores and the payload carries
        level=level.name,
        distance_m=window["distance_m"],
        width_m=window["width_m"],
        cardinal=window["cardinal"],
        visible=True,
    )


def attenuated_intensity(intensity: float, cloud_pct: float | None) -> float:
    """Geometric intensity dimmed by today's sky.

    Deliberately kept out of Exposure.level: the level is compared to what the
    species tolerates, which is a property of the spot, not of the weather. An
    attenuated level would make that alert flicker with every cloudy day.

    Unknown cloud cover changes nothing, like every other missing input here.
    """
    if cloud_pct is None:
        return intensity
    return intensity * (1 - CLOUD_ATTENUATION * float(cloud_pct) / 100)


def position_in_room(point: Point, vertices: list[Point], units_per_cm: float | None) -> str:
    """Corner, against a wall, or open floor — plain words for the notification."""
    # Thresholds in centimetres, converted once into plan units
    near = 30 * units_per_cm if units_per_cm else 15
    mid = 100 * units_per_cm if units_per_cm else 50

    distances = [
        math.dist(point, project_on_segment(point, a, b)[1]) for a, b in walls(vertices)
    ]
    closest = min(distances) if distances else float("inf")
    if closest <= near:
        # Two walls within reach means the plant sits in a corner
        return "dans un coin" if sum(1 for d in distances if d <= near) >= 2 else "contre un mur"
    return "près d'un mur" if closest <= mid else "en milieu de pièce"
