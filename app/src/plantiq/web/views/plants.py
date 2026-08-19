# app/src/plantiq/web/views/plants.py

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from psycopg.rows import dict_row

from plantiq.core.database import connect, query
from plantiq.engine.geometry import pull_inside
from plantiq.web.views.care import (
    ACTIONS,
    HEALTH_STATUSES,
    KINDS,
    LOGGABLE_ACTIONS,
    health_history,
    timeline,
)
from plantiq.web.views.equipment import TYPES as EQUIPMENT_LABELS
from plantiq.web.views.species import EXPOSURES, MONTHS, SEASONS, SUN_TOLERANCES

bp = Blueprint("plants", __name__, url_prefix="/plants")

# Plan units, half the editor grid. A guard against a misplaced marker, never a
# measurement: a room may not be calibrated when a plant is placed.
INSIDE_TOLERANCE = 10.0


def plant_count() -> int:
    return query("SELECT count(*) AS total FROM plant WHERE closed_at IS NULL", fetch="one")["total"]


# --- reads


def _open_rooms() -> list[dict]:
    """Only rooms carrying an open version — a closed room has no geometry left."""
    return query(
        """
        SELECT r.id, r.name, r.floor, s.name AS site_name,
               v.id AS version_id, v.environment, v.north_angle,
               v.scale_wall_index, v.scale_cm
        FROM room r
        JOIN site s ON s.id = r.site_id
        JOIN room_version v ON v.room_id = r.id AND v.closed_at IS NULL
        WHERE r.closed_at IS NULL AND s.closed_at IS NULL
        ORDER BY s.name, r.name
        """,
        fetch="all",
    )


def _version_geometry(version_ids: list[int]) -> dict[int, dict]:
    if not version_ids:
        return {}
    geometry: dict[int, dict] = {vid: {"vertices": [], "elements": []} for vid in version_ids}
    for row in query(
        "SELECT room_version_id, x, y FROM room_vertex "
        "WHERE room_version_id = ANY(%s) ORDER BY room_version_id, position",
        (version_ids,),
        fetch="all",
    ):
        geometry[row["room_version_id"]]["vertices"].append(
            {"x": float(row["x"]), "y": float(row["y"])}
        )
    for row in query(
        "SELECT room_version_id, wall_index, type, t_start, t_end FROM wall_element "
        "WHERE room_version_id = ANY(%s) AND closed_at IS NULL ORDER BY room_version_id, wall_index",
        (version_ids,),
        fetch="all",
    ):
        geometry[row["room_version_id"]]["elements"].append({
            "wall_index": row["wall_index"],
            "type": row["type"],
            "t_start": float(row["t_start"]),
            "t_end": float(row["t_end"]),
        })
    return geometry


def _load_plants() -> list[dict]:
    return query(
        """
        SELECT p.id, p.name, p.purchased_on, p.price_eur, p.retailer,
               sp.scientific_name,
               pl.id AS placement_id, pl.x, pl.y, pl.height_cm, pl.created_at AS placed_at,
               r.name AS room_name, s.name AS site_name,
               eq.name AS pot_name, eq.volume_l AS pot_volume_l, po.attached_on
        FROM plant p
        JOIN species sp ON sp.id = p.species_id
        JOIN plant_placement pl ON pl.plant_id = p.id AND pl.closed_at IS NULL
        JOIN room_version v ON v.id = pl.room_version_id
        JOIN room r ON r.id = v.room_id
        JOIN site s ON s.id = r.site_id
        LEFT JOIN plant_equipment po ON po.plant_id = p.id
               AND po.equipment_type = 'pot' AND po.closed_at IS NULL
        LEFT JOIN equipment eq ON eq.id = po.equipment_id
        WHERE p.closed_at IS NULL
        ORDER BY p.id
        """,
        fetch="all",
    )


def _placement(plant_id: int) -> dict | None:
    return query(
        """
        SELECT pl.id, pl.x, pl.y, pl.height_cm, pl.room_version_id,
               p.name AS plant_name, r.name AS room_name,
               v.scale_wall_index, v.scale_cm
        FROM plant_placement pl
        JOIN plant p ON p.id = pl.plant_id
        JOIN room_version v ON v.id = pl.room_version_id
        JOIN room r ON r.id = v.room_id
        WHERE pl.plant_id = %s AND pl.closed_at IS NULL
        """,
        (plant_id,),
        fetch="one",
    )


# --- validation


def _marker(payload: dict, vertices: list[dict]) -> tuple[dict | None, str | None]:
    """A marker is free of any wall, but must land inside the polygon."""
    point = (payload.get("x"), payload.get("y"))
    if not all(isinstance(value, int | float) for value in point):
        return None, "Poser le marqueur sur le plan."
    pulled = pull_inside(point, [(v["x"], v["y"]) for v in vertices], INSIDE_TOLERANCE)
    if pulled is None:
        return None, "Le marqueur doit être dans la pièce."
    return {"x": pulled[0], "y": pulled[1]}, None


def _height(payload: dict) -> tuple[float | None, str | None]:
    raw = payload.get("height_cm")
    if raw in (None, ""):
        return None, None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, "Hauteur non numérique."
    return (value, None) if value >= 0 else (None, "La hauteur ne peut pas être négative.")


def _price(payload: dict) -> tuple[float | None, str | None]:
    raw = payload.get("price_eur")
    if raw in (None, ""):
        return None, None
    try:
        value = float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None, "Prix non numérique."
    return (value, None) if value >= 0 else (None, "Le prix ne peut pas être négatif.")


# --- attached equipment


def _available(plant_id: int | None, kind: str) -> list[dict]:
    """Items of that kind which are free, plus the one this plant already uses."""
    return query(
        """
        SELECT e.id, e.name, e.volume_l, m.label AS material_label
        FROM equipment e
        LEFT JOIN material m ON m.id = e.material_id
        WHERE e.type = %s AND e.closed_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM plant_equipment p
              WHERE p.equipment_id = e.id AND p.closed_at IS NULL
                AND p.plant_id IS DISTINCT FROM %s
          )
        ORDER BY e.name
        """,
        (kind, plant_id),
        fetch="all",
    )


# --- routes


@bp.route("/")
def index():
    return render_template("plants/index.html", plants=_load_plants())


@bp.route("/new")
def new():
    rooms = _open_rooms()
    return render_template(
        "plants/new.html",
        rooms=rooms,
        geometry=_version_geometry([room["version_id"] for room in rooms]),
        species=query(
            "SELECT id, scientific_name FROM species ORDER BY scientific_name", fetch="all"
        ),
    )


@bp.route("/", methods=["POST"])
def create():
    payload = request.get_json(silent=True) or {}
    version_id = payload.get("room_version_id")

    if not payload.get("species_id") or not version_id:
        return jsonify(error="Choisir une espèce et une pièce."), 400
    if not (payload.get("name") or "").strip():
        return jsonify(error="Donner un nom à la plante."), 400

    geometry = _version_geometry([version_id]).get(version_id)
    if not geometry or len(geometry["vertices"]) < 3:
        return jsonify(error="Cette pièce n'a pas de géométrie exploitable."), 400

    marker, problem = _marker(payload, geometry["vertices"])
    if problem:
        return jsonify(error=problem), 400
    height, problem = _height(payload)
    if problem:
        return jsonify(error=problem), 400
    price, problem = _price(payload)
    if problem:
        return jsonify(error=problem), 400

    # A plant does not exist outside a place: both rows land together or not at all
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO plant (species_id, name, purchased_on, price_eur, retailer) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    payload["species_id"],
                    payload["name"].strip(),
                    (payload.get("purchased_on") or "").strip() or None,
                    price,
                    (payload.get("retailer") or "").strip() or None,
                ),
            )
            plant_id = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO plant_placement (plant_id, room_version_id, x, y, height_cm) "
                "VALUES (%s, %s, %s, %s, %s)",
                (plant_id, version_id, marker["x"], marker["y"], height),
            )
    return jsonify(id=plant_id, redirect=url_for("plants.index"))


@bp.route("/<int:plant_id>")
def detail(plant_id: int):
    plant = query(
        """
        SELECT p.*, sp.scientific_name, sp.common_name, sp.watering_ml_per_litre,
               sp.exposure_min, sp.exposure_max, sp.sun_tolerance,
               sp.temp_min_c, sp.temp_max_c,
               sp.fertilizing_interval_days, sp.fertilizing_month_start, sp.fertilizing_month_end,
               sp.repotting_interval_months, sp.repotting_month_start, sp.repotting_month_end,
               sp.id AS species_id
        FROM plant p JOIN species sp ON sp.id = p.species_id
        WHERE p.id = %s
        """,
        (plant_id,),
        fetch="one",
    )
    if plant is None:
        return "Plante introuvable", 404

    intervals = {
        row["season"]: row["interval_days"]
        for row in query(
            "SELECT season, interval_days FROM species_watering WHERE species_id = %s",
            (plant["species_id"],),
            fetch="all",
        )
    }

    placements = query(
        """
        SELECT pl.*, r.name AS room_name, r.floor, s.name AS site_name, s.city,
               v.environment, v.north_angle, v.scale_wall_index, v.scale_cm
        FROM plant_placement pl
        JOIN room_version v ON v.id = pl.room_version_id
        JOIN room r ON r.id = v.room_id
        JOIN site s ON s.id = r.site_id
        WHERE pl.plant_id = %s
        ORDER BY pl.created_at DESC
        """,
        (plant_id,),
        fetch="all",
    )
    pottings = query(
        """
        SELECT po.*, e.name AS equipment_name, e.type, e.volume_l, e.is_nursery_pot,
               e.outer_top_diameter_cm, e.outer_bottom_diameter_cm, e.outer_height_cm,
               po.equipment_type, e.has_drainage,
               e.purchased_on AS equipment_purchased_on, e.price_eur AS equipment_price_eur,
               e.retailer AS equipment_retailer, m.label AS material_label, m.is_porous
        FROM plant_equipment po
        JOIN equipment e ON e.id = po.equipment_id
        LEFT JOIN material m ON m.id = e.material_id
        WHERE po.plant_id = %s
        ORDER BY po.attached_on DESC NULLS LAST, po.id DESC
        """,
        (plant_id,),
        fetch="all",
    )

    current = next((p for p in placements if p["closed_at"] is None), None)
    current_pot = next(
        (p for p in pottings if p["closed_at"] is None and p["equipment_type"] == "pot"), None
    )
    current_cachepot = next(
        (p for p in pottings if p["closed_at"] is None and p["equipment_type"] == "cachepot"),
        None,
    )

    # Suggested watering volume: what the species asks per litre of substrate,
    # times what the current pot actually holds
    suggested_ml = None
    if current_pot and current_pot["volume_l"]:
        suggested_ml = round(float(current_pot["volume_l"]) * plant["watering_ml_per_litre"])

    kind = request.args.get("care", "all")
    if kind not in KINDS:
        kind = "all"
    geometry = (
        _version_geometry([current["room_version_id"]])[current["room_version_id"]]
        if current
        else {"vertices": [], "elements": []}
    )
    return render_template(
        "plants/detail.html",
        plant=plant,
        intervals=intervals,
        placements=placements,
        pottings=pottings,
        current_placement=current,
        current_potting=current_pot,
        current_cachepot=current_cachepot,
        labels=EQUIPMENT_LABELS,
        entries=timeline(plant_id, kind),
        health=health_history(plant_id),
        health_statuses=HEALTH_STATUSES,
        kind=kind,
        kinds=KINDS,
        actions=ACTIONS,
        loggable_actions=LOGGABLE_ACTIONS,
        suggested_ml=suggested_ml,
        geometry=geometry,
        seasons=SEASONS,
        exposures=EXPOSURES,
        sun_tolerances=SUN_TOLERANCES,
        months=MONTHS,
    )


@bp.route("/<int:plant_id>/move")
def move(plant_id: int):
    placement = _placement(plant_id)
    if placement is None:
        return "Plante introuvable", 404
    geometry = _version_geometry([placement["room_version_id"]])[placement["room_version_id"]]
    return render_template("plants/move.html", placement=placement, geometry=geometry)


@bp.route("/<int:plant_id>/move", methods=["POST"])
def save_move(plant_id: int):
    payload = request.get_json(silent=True) or {}
    placement = _placement(plant_id)
    if placement is None:
        return jsonify(error="Plante introuvable."), 404

    geometry = _version_geometry([placement["room_version_id"]])[placement["room_version_id"]]
    marker, problem = _marker(payload, geometry["vertices"])
    if problem:
        return jsonify(error=problem), 400
    height, problem = _height(payload)
    if problem:
        return jsonify(error=problem), 400

    # Only the user can tell a misplaced marker from a plant that actually moved
    if payload.get("reason") == "move":
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE plant_placement SET closed_at = now() WHERE id = %s", (placement["id"],)
                )
                cur.execute(
                    "INSERT INTO plant_placement (plant_id, room_version_id, x, y, height_cm) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (plant_id, placement["room_version_id"], marker["x"], marker["y"], height),
                )
    elif payload.get("reason") == "correction":
        query(
            "UPDATE plant_placement SET x = %s, y = %s, height_cm = %s WHERE id = %s",
            (marker["x"], marker["y"], height, placement["id"]),
        )
    else:
        return jsonify(error="Préciser s'il s'agit d'une correction ou d'un déplacement."), 400

    return jsonify(redirect=url_for("plants.index"))


@bp.route("/<int:plant_id>/pot")
def pot(plant_id: int):
    kind = request.args.get("kind", "pot")
    plant = query(
        "SELECT p.id, p.name, po.equipment_id, po.attached_on "
        "FROM plant p LEFT JOIN plant_equipment po ON po.plant_id = p.id "
        "     AND po.equipment_type = %s AND po.closed_at IS NULL "
        "WHERE p.id = %s AND p.closed_at IS NULL",
        (kind, plant_id),
        fetch="one",
    )
    if plant is None:
        return "Plante introuvable", 404
    return render_template(
        "plants/pot.html",
        plant=plant,
        pots=_available(plant_id, kind),
        kind=kind,
        labels=EQUIPMENT_LABELS,
        error=request.args.get("error"),
    )


@bp.route("/<int:plant_id>/pot", methods=["POST"])
def save_pot(plant_id: int):
    kind = (request.form.get("kind") or "pot").strip()
    equipment_id = (request.form.get("equipment_id") or "").strip()
    if not equipment_id:
        return redirect(
            url_for("plants.pot", plant_id=plant_id, kind=kind, error="Choisir un élément.")
        )

    # Repotting closes the running period and opens a new one, like every
    # other period in this model
    with connect() as conn:
        with conn.cursor() as cur:
            potted_on = (request.form.get("potted_on") or "").strip() or None
            cur.execute(
                "UPDATE plant_equipment SET closed_at = now(), detached_on = %s "
                "WHERE plant_id = %s AND equipment_type = %s AND closed_at IS NULL",
                (potted_on, plant_id, kind),
            )
            cur.execute(
                "INSERT INTO plant_equipment "
                "(plant_id, equipment_id, equipment_type, attached_on) "
                "SELECT %s, %s, e.type, %s FROM equipment e WHERE e.id = %s",
                (plant_id, int(equipment_id), potted_on, int(equipment_id)),
            )
    return redirect(url_for("plants.index"))


@bp.route("/<int:plant_id>/close", methods=["POST"])
def close(plant_id: int):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE plant_placement SET closed_at = now() "
                "WHERE plant_id = %s AND closed_at IS NULL",
                (plant_id,),
            )
            # Closing a plant frees the pot it occupied
            cur.execute(
                "UPDATE plant_equipment SET closed_at = now() "
                "WHERE plant_id = %s AND closed_at IS NULL",
                (plant_id,),
            )
            cur.execute(
                "UPDATE plant SET closed_at = now() WHERE id = %s AND closed_at IS NULL",
                (plant_id,),
            )
    return redirect(url_for("plants.index"))
