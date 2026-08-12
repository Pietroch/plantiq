# app/src/plantiq/web/views/home.py

from flask import Blueprint, render_template

from plantiq.core.database import query
from plantiq.web.views.rooms import room_count

bp = Blueprint("home", __name__)


@bp.route("/")
def index():
    site_count = query("SELECT count(*) AS total FROM site", fetch="one")["total"]
    return render_template("home.html", site_count=site_count, room_count=room_count())
