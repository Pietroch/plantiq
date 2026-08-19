# app/src/plantiq/web/views/equipment.py

from flask import Blueprint, redirect, render_template, request, url_for

from plantiq.core.database import query

bp = Blueprint("equipment", __name__, url_prefix="/equipment")

TYPES = {
    "pot": "Pot",
    "cachepot": "Cache-pot",
    "saucer": "Soucoupe",
    "stake": "Tuteur",
    "grow_light": "Lampe horticole",
    "humidifier": "Humidificateur",
    "substrate": "Substrat",
    "fertilizer": "Engrais",
    "tool": "Outil",
    "other": "Autre",
}

FIELDS = [
    "type", "name", "volume_l", "material_id",
    "outer_top_diameter_cm", "outer_bottom_diameter_cm", "outer_height_cm",
    "is_nursery_pot", "has_drainage", "purchased_on", "price_eur", "retailer",
]
COLUMNS = "id, " + ", ".join(FIELDS)


def _optional(name: str, cast) -> object | None:
    raw = (request.form.get(name) or "").strip()
    if not raw:
        return None
    try:
        return cast(raw.replace(",", "."))
    except ValueError:
        return None


def _tri_state(name: str) -> bool | None:
    """Yes, no, or unknown — drainage is meaningless on a lamp."""
    raw = request.form.get(name)
    return None if raw in (None, "", "unknown") else raw == "yes"


def _read_form() -> tuple[dict, str | None]:
    values = {
        "type": request.form.get("type"),
        "name": (request.form.get("name") or "").strip(),
        "volume_l": _optional("volume_l", float),
        "material_id": _optional("material_id", int),
        "outer_top_diameter_cm": _optional("outer_top_diameter_cm", float),
        "outer_bottom_diameter_cm": _optional("outer_bottom_diameter_cm", float),
        "outer_height_cm": _optional("outer_height_cm", float),
        "is_nursery_pot": bool(request.form.get("is_nursery_pot")),
        "has_drainage": _tri_state("has_drainage"),
        "purchased_on": (request.form.get("purchased_on") or "").strip() or None,
        "price_eur": _optional("price_eur", float),
        "retailer": (request.form.get("retailer") or "").strip() or None,
    }
    # A nursery pot came with the plant: no separate purchase to record
    if values["is_nursery_pot"]:
        values["purchased_on"] = values["price_eur"] = values["retailer"] = None
        if values["type"] != "pot":
            return values, "Un pot de culture est forcément de type Pot."
    if values["type"] not in TYPES:
        return values, "Type d'équipement inconnu."
    if not values["name"]:
        return values, "Le nom est obligatoire."
    if values["volume_l"] is not None and values["volume_l"] <= 0:
        return values, "Le volume doit être positif."
    if values["price_eur"] is not None and values["price_eur"] < 0:
        return values, "Le prix ne peut pas être négatif."
    for field in ("outer_top_diameter_cm", "outer_bottom_diameter_cm", "outer_height_cm"):
        if values[field] is not None and values[field] <= 0:
            return values, "Les dimensions doivent être positives."
    return values, None


def _materials() -> list[dict]:
    return query("SELECT id, label, is_porous FROM material ORDER BY label", fetch="all")


def _render_list(error: str | None = None, item: dict | None = None):
    rows = query(
        f"""
        SELECT {', '.join('e.' + f for f in FIELDS)}, e.id, e.closed_at,
               m.label AS material_label,
               p.plant_id, pl.name AS plant_name
        FROM equipment e
        LEFT JOIN material m  ON m.id = e.material_id
        LEFT JOIN plant_equipment p ON p.equipment_id = e.id AND p.closed_at IS NULL
        LEFT JOIN plant    pl ON pl.id = p.plant_id
        WHERE e.closed_at IS NULL
        ORDER BY e.type, e.name
        """,
        fetch="all",
    )
    return render_template(
        "equipment/index.html",
        equipment=rows,
        materials=_materials(),
        types=TYPES,
        item=item,
        error=error,
    )


@bp.route("/")
def index():
    return _render_list(error=request.args.get("error"))


@bp.route("/", methods=["POST"])
def create():
    values, problem = _read_form()
    if problem:
        return redirect(url_for("equipment.index", error=problem))
    query(
        f"INSERT INTO equipment ({', '.join(FIELDS)}) "
        f"VALUES ({', '.join(['%s'] * len(FIELDS))})",
        tuple(values[field] for field in FIELDS),
    )
    return redirect(url_for("equipment.index"))


@bp.route("/<int:equipment_id>/edit")
def edit(equipment_id: int):
    item = query(
        f"SELECT {COLUMNS} FROM equipment WHERE id = %s", (equipment_id,), fetch="one"
    )
    if item is None:
        return "Équipement introuvable", 404
    return render_template(
        "equipment/edit.html",
        item=item,
        materials=_materials(),
        types=TYPES,
        error=request.args.get("error"),
    )


@bp.route("/<int:equipment_id>/edit", methods=["POST"])
def update(equipment_id: int):
    values, problem = _read_form()
    if problem:
        return redirect(url_for("equipment.edit", equipment_id=equipment_id, error=problem))
    assignments = ", ".join(f"{field} = %s" for field in FIELDS)
    query(
        f"UPDATE equipment SET {assignments} WHERE id = %s",
        tuple(values[field] for field in FIELDS) + (equipment_id,),
    )
    return redirect(url_for("equipment.index"))


@bp.route("/<int:equipment_id>/close", methods=["POST"])
def close(equipment_id: int):
    # Closing an item detaches it from its plant: it holds nothing any more
    query(
        "UPDATE plant_equipment SET closed_at = now() "
        "WHERE equipment_id = %s AND closed_at IS NULL",
        (equipment_id,),
    )
    query(
        "UPDATE equipment SET closed_at = now() WHERE id = %s AND closed_at IS NULL",
        (equipment_id,),
    )
    return redirect(url_for("equipment.index"))
