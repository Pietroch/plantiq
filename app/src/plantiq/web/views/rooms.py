# app/src/plantiq/web/views/rooms.py

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from psycopg.rows import dict_row

from plantiq.core.database import connect, query
from plantiq.engine.geometry import is_simple, polygon_area, wall_lengths

bp = Blueprint("rooms", __name__, url_prefix="/rooms")

ELEMENT_LABELS = {"window": "Fenêtre", "radiator": "Radiateur", "air_conditioner": "Climatiseur"}
ENVIRONMENT_LABELS = {"indoor": "Intérieur", "outdoor": "Extérieur"}


def room_count() -> int:
    return query("SELECT count(*) AS total FROM room WHERE closed_at IS NULL", fetch="one")["total"]


def _open_sites() -> list[dict]:
    return query(
        "SELECT id, name, city FROM site WHERE closed_at IS NULL ORDER BY name", fetch="all"
    )


# --- measures


def _units_per_cm(points: list[tuple], scale_wall_index, scale_cm) -> float | None:
    """Derived from the reference wall, never stored — see the scale decision."""
    if scale_wall_index is None or not scale_cm:
        return None
    lengths = wall_lengths(points)
    if scale_wall_index >= len(lengths) or not lengths[scale_wall_index]:
        return None
    return lengths[scale_wall_index] / float(scale_cm)


def _measure(points: list[tuple], scale_wall_index, scale_cm) -> dict:
    """Wall lengths in centimetres, area in square metres — cm² says nothing about a room."""
    if len(points) < 3:
        return {"area": 0.0, "wall_lengths": [], "scaled": False}
    ratio = _units_per_cm(points, scale_wall_index, scale_cm)
    lengths = wall_lengths(points)
    area = polygon_area(points)
    if ratio:
        lengths = [length / ratio for length in lengths]
        area = area / (ratio**2) / 10_000
    return {"area": area, "wall_lengths": lengths, "scaled": bool(ratio)}


# --- validation


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


# --- reads


def _load_rooms() -> list[dict]:
    rooms = query(
        """
        SELECT r.id, r.name, r.floor, r.site_id, s.name AS site_name,
               v.id AS version_id, v.environment, v.north_angle,
               v.scale_wall_index, v.scale_cm
        FROM room r
        JOIN site s ON s.id = r.site_id
        LEFT JOIN room_version v ON v.room_id = r.id AND v.closed_at IS NULL
        WHERE r.closed_at IS NULL
        ORDER BY r.id
        """,
        fetch="all",
    )
    version_ids = [room["version_id"] for room in rooms if room["version_id"] is not None]
    if not version_ids:
        return [{**room, "vertices": [], "elements": [], "measures": _measure([], None, None)}
                for room in rooms]

    # Batch load, one query per child table rather than one per room
    vertices: dict[int, list] = {}
    for row in query(
        "SELECT room_version_id, position, x, y FROM room_vertex "
        "WHERE room_version_id = ANY(%s) ORDER BY room_version_id, position",
        (version_ids,),
        fetch="all",
    ):
        vertices.setdefault(row["room_version_id"], []).append(row)

    elements: dict[int, list] = {}
    for row in query(
        "SELECT room_version_id, wall_index, type, t_start, t_end FROM wall_element "
        "WHERE room_version_id = ANY(%s) AND closed_at IS NULL "
        "ORDER BY room_version_id, wall_index, t_start",
        (version_ids,),
        fetch="all",
    ):
        elements.setdefault(row["room_version_id"], []).append(row)

    result = []
    for room in rooms:
        own_vertices = vertices.get(room["version_id"], [])
        points = [(float(v["x"]), float(v["y"])) for v in own_vertices]
        result.append({
            **room,
            "vertices": own_vertices,
            "elements": elements.get(room["version_id"], []),
            "measures": _measure(points, room["scale_wall_index"], room["scale_cm"]),
        })
    return result


# --- writes


def _insert_room(payload: dict) -> int:
    """Room, version, vertices and elements land in a single transaction."""
    scale = payload.get("scale") or {}
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO room (site_id, name, floor) VALUES (%s, %s, %s) RETURNING id",
                (payload["site_id"], payload["name"], payload.get("floor")),
            )
            room_id = cur.fetchone()["id"]

            cur.execute(
                """
                INSERT INTO room_version
                       (room_id, environment, north_angle, scale_wall_index, scale_cm)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    room_id,
                    payload["environment"],
                    int(payload["north_angle"]),
                    scale.get("wall_index"),
                    scale.get("cm"),
                ),
            )
            version_id = cur.fetchone()["id"]

            cur.executemany(
                "INSERT INTO room_vertex (room_version_id, position, x, y) VALUES (%s, %s, %s, %s)",
                [
                    (version_id, position, vertex["x"], vertex["y"])
                    for position, vertex in enumerate(payload["vertices"])
                ],
            )

            elements = payload.get("elements") or []
            if elements:
                cur.executemany(
                    "INSERT INTO wall_element "
                    "(room_version_id, wall_index, type, t_start, t_end) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [
                        (version_id, item["wall_index"], item["type"], item["t_start"], item["t_end"])
                        for item in elements
                    ],
                )
    return room_id


# --- routes


@bp.route("/")
def index():
    return render_template(
        "rooms/index.html",
        rooms=_load_rooms(),
        labels=ELEMENT_LABELS,
        environments=ENVIRONMENT_LABELS,
    )


@bp.route("/new")
def new():
    return render_template("rooms/editor.html", labels=ELEMENT_LABELS, sites=_open_sites())


@bp.route("/", methods=["POST"])
def create():
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

    payload["name"] = (payload.get("name") or "").strip() or "Pièce sans nom"
    room_id = _insert_room(payload)
    return jsonify(id=room_id, redirect=url_for("rooms.index"))


@bp.route("/<int:room_id>/close", methods=["POST"])
def close(room_id: int):
    # Nothing is deleted anywhere — closing a room closes its open version too
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE room_version SET closed_at = now() "
                "WHERE room_id = %s AND closed_at IS NULL",
                (room_id,),
            )
            cur.execute(
                "UPDATE room SET closed_at = now() WHERE id = %s AND closed_at IS NULL",
                (room_id,),
            )
    return redirect(url_for("rooms.index"))
