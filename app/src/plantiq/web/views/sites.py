# app/src/plantiq/web/views/sites.py

from flask import Blueprint, redirect, render_template, request, url_for

from plantiq.core.database import query

bp = Blueprint("sites", __name__, url_prefix="/sites")

FIELDS = ["name", "address", "city", "country_code", "latitude", "longitude"]
OPTIONAL_FIELDS = ["address", "city", "country_code"]
COLUMNS = "id, " + ", ".join(FIELDS)


def _read_form() -> dict:
    values = {field: (request.form.get(field) or "").strip() for field in FIELDS}
    # Empty optional fields become NULL rather than empty strings
    for field in OPTIONAL_FIELDS:
        values[field] = values[field] or None
    # Coordinates are numeric in the table — a bad value raises, no validation yet
    values["latitude"] = float(values["latitude"])
    values["longitude"] = float(values["longitude"])
    return values


@bp.route("/")
def index():
    sites = query(
        f"SELECT {COLUMNS} FROM site WHERE closed_at IS NULL ORDER BY id", fetch="all"
    )
    return render_template("sites/index.html", sites=sites, fields=FIELDS)


@bp.route("/", methods=["POST"])
def create():
    values = _read_form()
    placeholders = ", ".join(["%s"] * len(FIELDS))
    query(
        f"INSERT INTO site ({', '.join(FIELDS)}) VALUES ({placeholders})",
        tuple(values[field] for field in FIELDS),
    )
    return redirect(url_for("sites.index"))


@bp.route("/<int:site_id>/edit")
def edit(site_id: int):
    site = query(f"SELECT {COLUMNS} FROM site WHERE id = %s", (site_id,), fetch="one")
    if site is None:
        return "Site introuvable", 404
    return render_template("sites/edit.html", site=site)


@bp.route("/<int:site_id>/edit", methods=["POST"])
def update(site_id: int):
    values = _read_form()
    assignments = ", ".join(f"{field} = %s" for field in FIELDS)
    query(
        f"UPDATE site SET {assignments} WHERE id = %s",
        tuple(values[field] for field in FIELDS) + (site_id,),
    )
    return redirect(url_for("sites.index"))


@bp.route("/<int:site_id>/close", methods=["POST"])
def close(site_id: int):
    # Nothing is deleted anywhere in this model — a site is closed, never removed
    query("UPDATE site SET closed_at = now() WHERE id = %s AND closed_at IS NULL", (site_id,))
    return redirect(url_for("sites.index"))
