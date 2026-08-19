# app/src/plantiq/web/views/notifications.py

from flask import Blueprint, render_template

from plantiq.core.database import query
from plantiq.web.views.care import ACTIONS

bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@bp.route("/")
def index():
    # Read-only: this table is written by the batch, it records what went out
    rows = query(
        """
        SELECT n.id, n.action, n.sent_on, n.sent_at, n.payload,
               n.reminder_id, r.due_on,
               p.id AS plant_id, p.name AS plant_name, s.timezone
        FROM notification_log n
        JOIN plant p ON p.id = n.plant_id
        LEFT JOIN reminder r ON r.id = n.reminder_id
        LEFT JOIN plant_placement pl ON pl.plant_id = p.id AND pl.closed_at IS NULL
        LEFT JOIN room_version v ON v.id = pl.room_version_id
        LEFT JOIN room ro ON ro.id = v.room_id
        LEFT JOIN site s ON s.id = ro.site_id
        ORDER BY n.sent_on DESC, n.sent_at DESC
        """,
        fetch="all",
    )
    return render_template("notifications/index.html", notifications=rows, actions=ACTIONS)
