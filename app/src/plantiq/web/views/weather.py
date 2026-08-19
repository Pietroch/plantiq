# app/src/plantiq/web/views/weather.py

from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request

from plantiq.core.database import query

bp = Blueprint("weather", __name__, url_prefix="/weather")

# OpenWeatherMap condition groups, by leading digit of condition_id
CONDITION_GROUPS = {
    2: "Orage",
    3: "Bruine",
    5: "Pluie",
    6: "Neige",
    7: "Brume",
    8: "Ciel",
}


def reading_count() -> int:
    return query("SELECT count(*) AS total FROM weather_log", fetch="one")["total"]


def _condition_label(condition_id: int | None) -> str:
    if condition_id is None:
        return "—"
    if condition_id == 800:
        return "Ciel dégagé"
    group = CONDITION_GROUPS.get(condition_id // 100, "Inconnu")
    return f"{group} ({condition_id})"


def _local(row: dict) -> dict:
    """timestamptz stores an absolute instant; the site's zone is the reading zone.

    Showing the stored value raw would display 21:37 for a measurement taken
    at 23:37 in Brussels — the storage is right, only the rendering was wrong.
    """
    zone = ZoneInfo(row["timezone"])
    return {
        **row,
        "condition_label": _condition_label(row["condition_id"]),
        "observed_at_local": row["observed_at"].astimezone(zone),
        "fetched_at_local": row["fetched_at"].astimezone(zone),
    }


@bp.route("/")
def index():
    # Read-only: this table is written by the daily batch, never by a form
    site_id = request.args.get("site_id", type=int)
    # The filter is built rather than passed as a nullable parameter:
    # "%s IS NULL" leaves Postgres unable to infer the parameter type
    clause = "WHERE w.site_id = %s" if site_id else ""
    rows = query(
        f"""
        SELECT w.site_id, s.name AS site_name, s.city, s.timezone,
               w.observed_on, w.observed_at, w.temp_c, w.humidity_pct,
               w.cloud_pct, w.condition_id, w.fetched_at
        FROM weather_log w
        JOIN site s ON s.id = w.site_id
        {clause}
        ORDER BY w.observed_on DESC, s.name
        """,
        (site_id,) if site_id else (),
        fetch="all",
    )
    return render_template(
        "weather/index.html",
        readings=[_local(row) for row in rows],
        sites=query(
            "SELECT id, name, city FROM site WHERE closed_at IS NULL ORDER BY name", fetch="all"
        ),
        selected_site=site_id,
    )
