# app/src/plantiq/web/views/runs.py

from flask import Blueprint, render_template

from plantiq.core.database import query

bp = Blueprint("runs", __name__, url_prefix="/runs")


@bp.route("/")
def index():
    # Read-only: written by the batch itself, one row per execution
    rows = query(
        """
        SELECT b.*,
               EXTRACT(EPOCH FROM (b.finished_at - b.started_at)) AS seconds,
               (SELECT count(*) FROM weather_log      w WHERE w.batch_run_id = b.id) AS readings,
               (SELECT count(*) FROM reminder         r WHERE r.batch_run_id = b.id) AS reminders,
               (SELECT count(*) FROM notification_log n WHERE n.batch_run_id = b.id) AS notifications
        FROM batch_run b
        ORDER BY b.started_at DESC
        LIMIT 60
        """,
        fetch="all",
    )
    return render_template("runs/index.html", runs=rows)
