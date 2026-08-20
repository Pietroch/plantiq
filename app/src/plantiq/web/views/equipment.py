# app/src/plantiq/web/views/equipment.py

from flask import Blueprint, redirect, render_template, request, url_for

from plantiq.core.database import query

bp = Blueprint("equipment", __name__, url_prefix="/equipment")

CONTAINER_TYPES = {"pot": "Pot", "cachepot": "Cache-pot"}
CONSUMABLE_TYPES = {"substrate": "Substrat", "fertilizer": "Engrais"}

# Bought once, recorded the same way everywhere
PURCHASE = {"purchased_on": "date", "price_eur": "float", "retailer": "text"}

# Business labels, defined once: the table headers and the form both read them,
# so a column never shows up as its SQL name in the interface.
FIELD_LABELS = {
    "type": "Type",
    "name": "Nom",
    "volume_l": "Volume",
    "material_id": "Matière",
    "outer_top_diameter_cm": "Diamètre haut",
    "outer_bottom_diameter_cm": "Diamètre bas",
    "outer_height_cm": "Hauteur",
    "is_nursery_pot": "Pot de culture",
    "has_drainage": "Drainage",
    "npk": "NPK",
    "dilution_ml_per_l": "Dilution",
    "purchased_on": "Acheté le",
    "price_eur": "Prix",
    "retailer": "Vendeur",
}

# Short units for the table headers; the form spells them out next to the input
FIELD_UNITS = {
    "volume_l": "L",
    "outer_top_diameter_cm": "cm",
    "outer_bottom_diameter_cm": "cm",
    "outer_height_cm": "cm",
    "dilution_ml_per_l": "ml/L",
    "price_eur": "€",
}

# Three tables, three life cycles: a container is kept, a consumable is used
# up, a tool belongs to no plant. Each entry drives the SELECT, the INSERT, the
# UPDATE and the form — adding a column is a one-line change.
TABLES = {
    "container": {
        "label": "Contenants",
        "types": CONTAINER_TYPES,
        # The litres a pot holds are the litres watering_ml_per_litre multiplies,
        # which a bare "Volume" does not say
        "labels": {"volume_l": "Volume de substrat"},
        "fields": {
            "type": "choice",
            "name": "text",
            "volume_l": "float",
            "material_id": "material",
            "outer_top_diameter_cm": "float",
            "outer_bottom_diameter_cm": "float",
            "outer_height_cm": "float",
            "is_nursery_pot": "bool",
            "has_drainage": "tri",
            **PURCHASE,
        },
    },
    "consumable": {
        "label": "Consommables",
        "types": CONSUMABLE_TYPES,
        "fields": {
            "type": "choice",
            "name": "text",
            "volume_l": "float",
            "npk": "text",
            "dilution_ml_per_l": "float",
            **PURCHASE,
        },
    },
    "tool": {
        "label": "Outils",
        "types": None,
        "fields": {"name": "text", **PURCHASE},
    },
}

POSITIVE = (
    "volume_l",
    "dilution_ml_per_l",
    "outer_top_diameter_cm",
    "outer_bottom_diameter_cm",
    "outer_height_cm",
)


def _value(name: str, kind: str):
    raw = (request.form.get(name) or "").strip()
    if kind == "bool":
        return bool(request.form.get(name))
    if kind == "tri":
        # Yes, no, or unknown — a missing drainage value is not a missing hole
        return None if raw in ("", "unknown") else raw == "yes"
    if kind in ("float", "material"):
        if not raw:
            return None
        try:
            return float(raw.replace(",", ".")) if kind == "float" else int(raw)
        except ValueError:
            return None
    return raw or None


def _read_form(spec: dict) -> tuple[dict, str | None]:
    values = {name: _value(name, kind) for name, kind in spec["fields"].items()}

    if spec["types"] and values["type"] not in spec["types"]:
        return values, "Type inconnu."
    if not values["name"]:
        return values, "Le nom est obligatoire."
    # A nursery pot came with the plant: no separate purchase to record
    if values.get("is_nursery_pot"):
        values["purchased_on"] = values["price_eur"] = values["retailer"] = None
        if values["type"] != "pot":
            return values, "Un pot de culture est forcément de type Pot."
    for name in POSITIVE:
        if values.get(name) is not None and values[name] <= 0:
            return values, "Les volumes et les dimensions doivent être positifs."
    if values.get("price_eur") is not None and values["price_eur"] < 0:
        return values, "Le prix ne peut pas être négatif."
    if values.get("type") != "fertilizer" and (
        values.get("npk") or values.get("dilution_ml_per_l")
    ):
        return values, "Le NPK et la dilution ne concernent que les engrais."
    return values, None


def _materials() -> list[dict]:
    return query("SELECT id, label, is_porous FROM material ORDER BY label", fetch="all")


def _rows(table: str) -> list[dict]:
    if table == "container":
        # Which plant holds it, so a free container is visible at a glance
        return query(
            """
            SELECT c.*, m.label AS material_label, pl.name AS plant_name
            FROM container c
            LEFT JOIN material m ON m.id = c.material_id
            LEFT JOIN plant_container pc ON pc.container_id = c.id AND pc.closed_at IS NULL
            LEFT JOIN plant pl ON pl.id = pc.plant_id
            WHERE c.closed_at IS NULL
            ORDER BY c.type, c.name
            """,
            fetch="all",
        )
    return query(f"SELECT * FROM {table} WHERE closed_at IS NULL ORDER BY name", fetch="all")


def _spec(table: str) -> dict | None:
    # Table names come from TABLES only, never from the request path itself
    return TABLES.get(table)


def _labels() -> dict[str, dict[str, str]]:
    """Header text per table and per field, unit included.

    Resolved here rather than in the templates: the table and the form must
    name a column the same way, and a per-table override stays possible.
    """
    resolved = {}
    for table, spec in TABLES.items():
        own = spec.get("labels", {})
        resolved[table] = {
            field: own.get(field) or FIELD_LABELS[field] for field in spec["fields"]
        }
    return resolved


@bp.route("/")
def index():
    return render_template(
        "equipment/index.html",
        tables=TABLES,
        rows={table: _rows(table) for table in TABLES},
        materials=_materials(),
        types={**CONTAINER_TYPES, **CONSUMABLE_TYPES},
        labels=_labels(),
        units=FIELD_UNITS,
        error=request.args.get("error"),
    )


@bp.route("/<table>/", methods=["POST"])
def create(table: str):
    spec = _spec(table)
    if spec is None:
        return "Table inconnue", 404
    values, problem = _read_form(spec)
    if problem:
        return redirect(url_for("equipment.index", error=problem))
    columns = list(values)
    query(
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(['%s'] * len(columns))})",
        tuple(values.values()),
    )
    return redirect(url_for("equipment.index"))


@bp.route("/<table>/<int:item_id>/edit")
def edit(table: str, item_id: int):
    spec = _spec(table)
    if spec is None:
        return "Table inconnue", 404
    item = query(f"SELECT * FROM {table} WHERE id = %s", (item_id,), fetch="one")
    if item is None:
        return "Élément introuvable", 404
    return render_template(
        "equipment/edit.html",
        table=table,
        spec=spec,
        item=item,
        materials=_materials(),
        labels=_labels(),
        units=FIELD_UNITS,
        error=request.args.get("error"),
    )


@bp.route("/<table>/<int:item_id>/edit", methods=["POST"])
def update(table: str, item_id: int):
    spec = _spec(table)
    if spec is None:
        return "Table inconnue", 404
    values, problem = _read_form(spec)
    if problem:
        return redirect(url_for("equipment.edit", table=table, item_id=item_id, error=problem))
    assignments = ", ".join(f"{column} = %s" for column in values)
    query(
        f"UPDATE {table} SET {assignments} WHERE id = %s",
        tuple(values.values()) + (item_id,),
    )
    return redirect(url_for("equipment.index"))


@bp.route("/<table>/<int:item_id>/close", methods=["POST"])
def close(table: str, item_id: int):
    if _spec(table) is None:
        return "Table inconnue", 404
    if table == "container":
        # Closing a container detaches it: it holds nothing any more
        query(
            "UPDATE plant_container SET closed_at = now() "
            "WHERE container_id = %s AND closed_at IS NULL",
            (item_id,),
        )
    query(
        f"UPDATE {table} SET closed_at = now() WHERE id = %s AND closed_at IS NULL",
        (item_id,),
    )
    return redirect(url_for("equipment.index"))
