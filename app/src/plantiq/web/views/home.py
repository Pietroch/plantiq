# app/src/plantiq/web/views/home.py

from flask import Blueprint, render_template

from plantiq.core.database import query
from plantiq.web.views.plants import plant_count
from plantiq.web.views.rooms import room_count
from plantiq.web.views.weather import reading_count

bp = Blueprint("home", __name__)


@bp.route("/")
def index():
    return render_template(
        "home.html",
        site_count=query(
            "SELECT count(*) AS total FROM site WHERE closed_at IS NULL", fetch="one"
        )["total"],
        room_count=room_count(),
        plant_count=plant_count(),
        reading_count=reading_count(),
    )
