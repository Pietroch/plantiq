# app/src/plantiq/web/views/care.py

from flask import Blueprint, redirect, request, url_for
from psycopg.rows import dict_row

from plantiq.core.database import connect, query

bp = Blueprint("care", __name__, url_prefix="/care")

ACTIONS = {
    "watering": "Arrosage",
    "fertilizing": "Fertilisation",
    "repotting": "Rempotage",
    "pruning": "Taille",
    "treatment": "Traitement",
    "cleaning": "Nettoyage",
}

# repotting is excluded by a CHECK on care_log: the act lives in potting
LOGGABLE_ACTIONS = {key: label for key, label in ACTIONS.items() if key != "repotting"}

HEALTH_STATUSES = {
    "healthy": "En bonne santé",
    "dormant": "En dormance",
    "stressed": "Stressée",
    "sick": "Malade",
    "recovering": "En convalescence",
    "dying": "Mourante",
}

KINDS = {
    "all": "Tous",
    "pending": "En attente",
    "done": "Exécutés",
    "sent": "Notifiés",
}


def timeline(plant_id: int, kind: str = "all") -> list[dict]:
    """Reminders, care and notifications merged into one list, most recent first."""
    entries: list[dict] = []

    if kind in ("all", "pending"):
        for row in query(
            "SELECT id, action, due_on, is_generated, completed_at, dismissed_reason, care_log_id "
            "FROM reminder WHERE plant_id = %s AND completed_at IS NULL ORDER BY due_on",
            (plant_id,),
            fetch="all",
        ):
            entries.append({**row, "kind": "pending", "date": row["due_on"]})

    if kind in ("all", "done"):
        for row in query(
            "SELECT id, action, done_at, recorded_at, volume_ml, notes "
            "FROM care_log WHERE plant_id = %s ORDER BY done_at DESC",
            (plant_id,),
            fetch="all",
        ):
            entries.append({**row, "kind": "done", "date": row["done_at"].date()})

    if kind in ("all", "sent"):
        for row in query(
            "SELECT id, action, sent_on, sent_at, reminder_id "
            "FROM notification_log WHERE plant_id = %s ORDER BY sent_on DESC",
            (plant_id,),
            fetch="all",
        ):
            entries.append({**row, "kind": "sent", "date": row["sent_on"]})

    return sorted(entries, key=lambda entry: entry["date"], reverse=True)


def _back(plant_id: int):
    return redirect(url_for("plants.detail", plant_id=plant_id) + "#soins")


def _form_date(name: str) -> str | None:
    return (request.form.get(name) or "").strip() or None


@bp.route("/reminders/<int:reminder_id>/complete", methods=["POST"])
def complete(reminder_id: int):
    """Validating a task writes the care and closes the reminder, in one go."""
    reminder = query(
        "SELECT id, plant_id, action FROM reminder WHERE id = %s AND completed_at IS NULL",
        (reminder_id,),
        fetch="one",
    )
    if reminder is None:
        return "Rappel introuvable", 404

    done_on = _form_date("done_on")
    volume = (request.form.get("volume_ml") or "").strip() or None

    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # A repotting reminder has no care_log counterpart: it is closed alone
            care_id = None
            if reminder["action"] != "repotting":
                cur.execute(
                    "INSERT INTO care_log (plant_id, action, done_at, volume_ml, notes) "
                    "VALUES (%s, %s, COALESCE(%s::timestamptz, now()), %s, %s) RETURNING id",
                    (
                        reminder["plant_id"],
                        reminder["action"],
                        done_on,
                        int(volume) if volume else None,
                        (request.form.get("notes") or "").strip() or None,
                    ),
                )
                care_id = cur.fetchone()["id"]
            cur.execute(
                "UPDATE reminder SET completed_at = now(), care_log_id = %s WHERE id = %s",
                (care_id, reminder_id),
            )
    return _back(reminder["plant_id"])


@bp.route("/reminders/<int:reminder_id>/dismiss", methods=["POST"])
def dismiss(reminder_id: int):
    """Closed without any care: the task no longer applies."""
    reminder = query("SELECT plant_id FROM reminder WHERE id = %s", (reminder_id,), fetch="one")
    if reminder is None:
        return "Rappel introuvable", 404
    query(
        "UPDATE reminder SET completed_at = now(), dismissed_reason = %s "
        "WHERE id = %s AND completed_at IS NULL",
        ((request.form.get("dismissed_reason") or "").strip() or "sans objet", reminder_id),
    )
    return _back(reminder["plant_id"])


@bp.route("/plants/<int:plant_id>/add", methods=["POST"])
def add(plant_id: int):
    """A care carried out without any reminder — a missed watering caught up later."""
    action = request.form.get("action")
    if action not in LOGGABLE_ACTIONS:
        return "Action inconnue", 400
    volume = (request.form.get("volume_ml") or "").strip() or None
    query(
        "INSERT INTO care_log (plant_id, action, done_at, volume_ml, notes) "
        "VALUES (%s, %s, COALESCE(%s::timestamptz, now()), %s, %s)",
        (
            plant_id,
            action,
            _form_date("done_on"),
            int(volume) if volume else None,
            (request.form.get("notes") or "").strip() or None,
        ),
    )
    return _back(plant_id)


@bp.route("/<int:care_id>/edit", methods=["POST"])
def edit(care_id: int):
    # Corrected in place: one writer, no audit trail wanted
    care = query("SELECT plant_id FROM care_log WHERE id = %s", (care_id,), fetch="one")
    if care is None:
        return "Soin introuvable", 404
    volume = (request.form.get("volume_ml") or "").strip() or None
    query(
        "UPDATE care_log SET action = %s, done_at = COALESCE(%s::timestamptz, done_at), "
        "volume_ml = %s, notes = %s WHERE id = %s",
        (
            request.form.get("action"),
            _form_date("done_on"),
            int(volume) if volume else None,
            (request.form.get("notes") or "").strip() or None,
            care_id,
        ),
    )
    return _back(care["plant_id"])


@bp.route("/<int:care_id>/delete", methods=["POST"])
def delete(care_id: int):
    care = query("SELECT plant_id FROM care_log WHERE id = %s", (care_id,), fetch="one")
    if care is None:
        return "Soin introuvable", 404
    with connect() as conn:
        with conn.cursor() as cur:
            # A reminder pointing at it would keep a dangling reference
            cur.execute(
                "UPDATE reminder SET care_log_id = NULL WHERE care_log_id = %s", (care_id,)
            )
            cur.execute("DELETE FROM care_log WHERE id = %s", (care_id,))
    return _back(care["plant_id"])


# --- health observations


def health_history(plant_id: int) -> list[dict]:
    """Every observation, most recent first. The first row is the current state."""
    return query(
        "SELECT id, status, noted_on, note, recorded_at FROM plant_health "
        "WHERE plant_id = %s ORDER BY noted_on DESC, id DESC",
        (plant_id,),
        fetch="all",
    )


@bp.route("/plants/<int:plant_id>/health", methods=["POST"])
def add_health(plant_id: int):
    """Append only: a new observation never overwrites the previous one."""
    status = request.form.get("status")
    if status not in HEALTH_STATUSES:
        return "Statut inconnu", 400
    query(
        "INSERT INTO plant_health (plant_id, status, noted_on, note) "
        "VALUES (%s, %s, COALESCE(%s::date, CURRENT_DATE), %s)",
        (
            plant_id,
            status,
            _form_date("noted_on"),
            (request.form.get("note") or "").strip() or None,
        ),
    )
    return redirect(url_for("plants.detail", plant_id=plant_id) + "#sante")


@bp.route("/health/<int:health_id>/delete", methods=["POST"])
def delete_health(health_id: int):
    # A mistyped observation is removed outright: one writer, no audit trail
    row = query("SELECT plant_id FROM plant_health WHERE id = %s", (health_id,), fetch="one")
    if row is None:
        return "Observation introuvable", 404
    query("DELETE FROM plant_health WHERE id = %s", (health_id,))
    return redirect(url_for("plants.detail", plant_id=row["plant_id"]) + "#sante")
