# app/src/plantiq/web/views/rooms.py

from datetime import UTC, datetime

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from plantiq.core.database import query
from plantiq.engine.geometry import is_simple, polygon_area, wall_lengths

bp = Blueprint("rooms", __name__, url_prefix="/rooms")

ELEMENT_LABELS = {"window": "Fenêtre", "radiator": "Radiateur", "air_conditioner": "Climatiseur"}
ENVIRONMENT_LABELS = {"indoor": "Intérieur", "outdoor": "Extérieur"}

# Temporary in-memory storage — the room tables do not exist yet
_rooms: list[dict] = []
_next_id = 1


def room_count() -> int:
    return sum(1 for room in _rooms if room["closed_at"] is None)


def _open_sites() -> list[dict]:
    return query(
        "SELECT id, name, city FROM site WHERE closed_at IS NULL ORDER BY name", fetch="all"
    )


def _points(room: dict) -> list[tuple[float, float]]:
    return [(v["x"], v["y"]) for v in room["vertices"]]


def _units_per_cm(room: dict) -> float | None:
    """Derived from the reference wall, never stored — see the scale decision."""
    scale = room.get("scale")
    if not scale:
        return None
    lengths = wall_lengths(_points(room))
    index = scale["wall_index"]
    if index >= len(lengths) or not lengths[index] or not scale.get("cm"):
        return None
    return lengths[index] / scale["cm"]


def _measure(room: dict) -> dict:
    """Wall lengths in centimetres, area in square metres — cm² says nothing about a room."""
    points = _points(room)
    ratio = _units_per_cm(room)
    lengths = wall_lengths(points)
    area = polygon_area(points)
    if ratio:
        lengths = [length / ratio for length in lengths]
        area = area / (ratio**2) / 10_000
    return {"area": area, "wall_lengths": lengths, "scaled": bool(ratio)}


def _validate(payload: dict, wall_total: int) -> str | None:
    if payload.get("site_id") is None:
        return "Une pièce doit appartenir à un site."
    if not payload.get("closed"):
        return "Le contour doit être fermé."
    if payload.get("environment") not in ENVIRONMENT_LABELS:
        return "Milieu inconnu."

    angle = payload.get("north_angle")
    if not isinstance(angle, int | float) or not 0 <= angle < 360:
        return "L'angle du nord doit être compris entre 0 et 360."

    for item in payload.get("elements") or []:
        if item.get("type") not in ELEMENT_LABELS:
            return "Type d'élément inconnu."
        index = item.get("wall_index")
        if not isinstance(index, int) or not 0 <= index < wall_total:
            return f"Élément posé sur un mur inexistant ({index})."
        start, end = item.get("t_start"), item.get("t_end")
        if not isinstance(start, int | float) or not isinstance(end, int | float):
            return "Bornes d'élément non numériques."
        if not 0 <= start < end <= 1:
            return "Un élément doit vérifier 0 <= début < fin <= 1."

    scale = payload.get("scale")
    if scale is not None:
        index = scale.get("wall_index")
        if not isinstance(index, int) or not 0 <= index < wall_total:
            return "Le mur de référence n'existe pas."
        if not isinstance(scale.get("cm"), int | float) or scale["cm"] <= 0:
            return "La longueur de référence doit être positive."
    return None


@bp.route("/")
def index():
    rooms = [{**room, "measures": _measure(room)} for room in _rooms]
    return render_template(
        "rooms/index.html", rooms=rooms, labels=ELEMENT_LABELS, environments=ENVIRONMENT_LABELS
    )


@bp.route("/new")
def new():
    return render_template("rooms/editor.html", labels=ELEMENT_LABELS, sites=_open_sites())


@bp.route("/", methods=["POST"])
def create():
    global _next_id
    payload = request.get_json(silent=True) or {}
    vertices = payload.get("vertices") or []

    if len(vertices) < 3:
        return jsonify(error="Une pièce a besoin d'au moins trois sommets."), 400

    points = [(v["x"], v["y"]) for v in vertices]
    if not is_simple(points):
        return jsonify(error="Le contour se croise lui-même."), 400

    # A closed outline has as many walls as vertices
    problem = _validate(payload, wall_total=len(vertices))
    if problem:
        return jsonify(error=problem), 400

    room = {
        "id": _next_id,
        "site_id": payload["site_id"],
        "name": (payload.get("name") or "").strip() or f"Pièce {_next_id}",
        "floor": payload.get("floor"),
        "environment": payload["environment"],
        "north_angle": payload["north_angle"],
        "scale": payload.get("scale"),
        "vertices": vertices,
        "elements": payload.get("elements") or [],
        "closed_at": None,
    }
    _next_id += 1
    _rooms.append(room)
    return jsonify(id=room["id"], redirect=url_for("rooms.index"))


@bp.route("/<int:room_id>/close", methods=["POST"])
def close(room_id: int):
    # Nothing is deleted anywhere in this model — a room is closed, never removed
    for room in _rooms:
        if room["id"] == room_id and room["closed_at"] is None:
            room["closed_at"] = datetime.now(UTC)
    return redirect(url_for("rooms.index"))
