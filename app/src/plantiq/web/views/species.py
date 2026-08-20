# app/src/plantiq/web/views/species.py

from flask import Blueprint, redirect, render_template, request, url_for
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from plantiq.core.database import connect, query
from plantiq.engine.light import ExposureLevel

bp = Blueprint("species", __name__, url_prefix="/species")

SEASONS = {"spring": "Printemps", "summer": "Été", "autumn": "Automne", "winter": "Hiver"}
EXPOSURES = {
    "low": "Faible",
    "indirect": "Indirecte",
    "bright_indirect": "Vive indirecte",
    "direct": "Directe",
}
SUN_TOLERANCES = {"none": "Aucune", "filtered": "Filtrée", "full": "Plein soleil"}
MONTHS = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}

COLUMNS = """
    id, scientific_name, common_name, watering_ml_per_litre,
    exposure_min, exposure_max, sun_tolerance, temp_min_c, temp_max_c, humidity_min_pct,
    fertilizing_interval_days, fertilizing_month_start, fertilizing_month_end,
    repotting_interval_months, repotting_month_start, repotting_month_end
"""


def _optional_int(name: str) -> int | None:
    raw = (request.form.get(name) or "").strip()
    return int(raw) if raw else None


def _read_form() -> tuple[dict, dict[str, int], str | None]:
    values = {
        "scientific_name": (request.form.get("scientific_name") or "").strip(),
        "common_name": (request.form.get("common_name") or "").strip() or None,
        "watering_ml_per_litre": _optional_int("watering_ml_per_litre"),
        "exposure_min": request.form.get("exposure_min"),
        "exposure_max": request.form.get("exposure_max"),
        "sun_tolerance": request.form.get("sun_tolerance"),
        "temp_min_c": _optional_int("temp_min_c"),
        "temp_max_c": _optional_int("temp_max_c"),
        "humidity_min_pct": _optional_int("humidity_min_pct"),
        "fertilizing_interval_days": _optional_int("fertilizing_interval_days"),
        "fertilizing_month_start": _optional_int("fertilizing_month_start"),
        "fertilizing_month_end": _optional_int("fertilizing_month_end"),
        "repotting_interval_months": _optional_int("repotting_interval_months"),
        "repotting_month_start": _optional_int("repotting_month_start"),
        "repotting_month_end": _optional_int("repotting_month_end"),
    }
    intervals = {season: _optional_int(f"interval_{season}") for season in SEASONS}

    if not values["scientific_name"]:
        return values, intervals, "Le nom scientifique est obligatoire."
    if values["exposure_min"] not in EXPOSURES or values["exposure_max"] not in EXPOSURES:
        return values, intervals, "Exposition inconnue."
    if ExposureLevel[values["exposure_max"]] < ExposureLevel[values["exposure_min"]]:
        return values, intervals, "L'exposition maximale doit être au moins égale à la minimale."
    if values["sun_tolerance"] not in SUN_TOLERANCES:
        return values, intervals, "Tolérance au soleil inconnue."
    if not values["watering_ml_per_litre"] or values["watering_ml_per_litre"] <= 0:
        return values, intervals, "Le volume d'arrosage par litre doit être positif."
    if values["temp_min_c"] is None or values["temp_max_c"] is None:
        return values, intervals, "Les deux températures sont obligatoires."
    if values["temp_max_c"] <= values["temp_min_c"]:
        return values, intervals, "La température maximale doit dépasser la minimale."
    humidity = values["humidity_min_pct"]
    if humidity is not None and not 0 <= humidity <= 100:
        return values, intervals, "L'humidité minimale doit être comprise entre 0 et 100 %."

    # The database cannot check this one: a species carries all four seasons
    missing = [SEASONS[s] for s, days in intervals.items() if not days or days <= 0]
    if missing:
        return values, intervals, f"Intervalle d'arrosage manquant : {', '.join(missing)}."

    for field in ("fertilizing", "repotting"):
        start, end = values[f"{field}_month_start"], values[f"{field}_month_end"]
        if (start is None) != (end is None):
            return values, intervals, "Une fenêtre de mois se donne entière ou pas du tout."
    return values, intervals, None


@bp.route("/")
def index():
    rows = query(f"SELECT {COLUMNS} FROM species ORDER BY scientific_name", fetch="all")
    intervals: dict[int, dict] = {}
    for row in query(
        "SELECT species_id, season, interval_days FROM species_watering", fetch="all"
    ):
        intervals.setdefault(row["species_id"], {})[row["season"]] = row["interval_days"]
    return render_template(
        "species/index.html",
        species=rows,
        intervals=intervals,
        seasons=SEASONS,
        exposures=EXPOSURES,
        sun_tolerances=SUN_TOLERANCES,
        months=MONTHS,
        error=request.args.get("error"),
    )


@bp.route("/", methods=["POST"])
def create():
    values, intervals, problem = _read_form()
    if problem:
        return redirect(url_for("species.index", error=problem))

    # Species and its four seasons land together or not at all
    try:
        with connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                columns = list(values)
                cur.execute(
                    f"INSERT INTO species ({', '.join(columns)}) "
                    f"VALUES ({', '.join(['%s'] * len(columns))}) RETURNING id",
                    tuple(values[column] for column in columns),
                )
                species_id = cur.fetchone()["id"]
                cur.executemany(
                    "INSERT INTO species_watering (species_id, season, interval_days) "
                    "VALUES (%s, %s, %s)",
                    [(species_id, season, days) for season, days in intervals.items()],
                )
    except UniqueViolation:
        # scientific_name is unique: a foreseeable mistake, not a crash
        return redirect(
            url_for("species.index", error=f"« {values['scientific_name']} » existe déjà.")
        )
    return redirect(url_for("species.index"))


@bp.route("/<int:species_id>/edit")
def edit(species_id: int):
    item = query(f"SELECT {COLUMNS} FROM species WHERE id = %s", (species_id,), fetch="one")
    if item is None:
        return "Espèce introuvable", 404
    intervals = {
        row["season"]: row["interval_days"]
        for row in query(
            "SELECT season, interval_days FROM species_watering WHERE species_id = %s",
            (species_id,),
            fetch="all",
        )
    }
    return render_template(
        "species/edit.html",
        item=item,
        intervals=intervals,
        seasons=SEASONS,
        exposures=EXPOSURES,
        sun_tolerances=SUN_TOLERANCES,
        months=MONTHS,
        error=request.args.get("error"),
    )


@bp.route("/<int:species_id>/edit", methods=["POST"])
def update(species_id: int):
    values, intervals, problem = _read_form()
    if problem:
        return redirect(url_for("species.edit", species_id=species_id, error=problem))

    assignments = ", ".join(f"{column} = %s" for column in values)
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE species SET {assignments} WHERE id = %s",
                    tuple(values.values()) + (species_id,),
                )
                # The four seasons always exist, so an upsert rather than delete-then-insert
                cur.executemany(
                    "INSERT INTO species_watering (species_id, season, interval_days) "
                    "VALUES (%s, %s, %s) "
                    "ON CONFLICT (species_id, season) DO UPDATE SET interval_days = EXCLUDED.interval_days",
                    [(species_id, season, days) for season, days in intervals.items()],
                )
    except UniqueViolation:
        return redirect(
            url_for(
                "species.edit",
                species_id=species_id,
                error=f"« {values['scientific_name']} » existe déjà.",
            )
        )
    return redirect(url_for("species.index"))
