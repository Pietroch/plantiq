# app/src/plantiq/run.py

import json
from datetime import date

from psycopg.rows import dict_row

from plantiq import weather
from plantiq.adapters.notify import send
from plantiq.core.database import connect, query
from plantiq.core.logging import get_logger
from plantiq.engine.rules import assess_all, context, generate, message

log = get_logger(__name__)

# Resend policy, by action: delay between two notifications, and how many
# resends after the first one. Watering is urgent, the others are planned.
RESEND = {
    "watering": {"delay_days": 3, "max_resends": 3},
    "fertilizing": {"delay_days": 7, "max_resends": 2},
    "repotting": {"delay_days": 7, "max_resends": 2},
}

# A real run takes seconds. Past this, a row still 'running' is a run that died
# without reporting back, and the next run says so instead of leaving it open.
STALE_RUN_MINUTES = 15


def _open_plants() -> list[int]:
    return [
        row["id"]
        for row in query("SELECT id FROM plant WHERE closed_at IS NULL ORDER BY id", fetch="all")
    ]


# DETTE — la sélection ci-dessous compare due_on à une date UTC, alors que
# generate() et preview() raisonnent dans le fuseau du site via ctx.today.
# Les chemins de DÉCISION sont unifiés (assess, send_decision), la SÉLECTION
# des rappels échus ne l'est pas : entre minuit et 2 h heure belge en été, ce
# comparateur retarde d'un jour sur le reste du moteur.
# Sans effet à 16 h UTC, l'heure du cron. À corriger en passant la date du site.
def _due_reminders(today: date) -> list[dict]:
    return query(
        "SELECT id, plant_id, action, due_on FROM reminder "
        "WHERE completed_at IS NULL AND due_on <= %s ORDER BY plant_id, due_on",
        (today,),
        fetch="all",
    )


def send_decision(plant_id: int, action: str, ctx) -> tuple[bool, str]:
    """Whether a notification would go out, and why. Read-only, used by both
    the batch and the preview so the two can never disagree.

    The delay counts from the most recent of two events: the last care done or
    the last notification sent. The returned reason names which one was used —
    "resend in 4 days" is otherwise a black box.
    """
    policy = RESEND.get(action, RESEND["fertilizing"])
    reminder = query(
        "SELECT id FROM reminder WHERE plant_id = %s AND action = %s AND completed_at IS NULL",
        (plant_id, action),
        fetch="one",
    )
    if reminder is None:
        return True, "premier envoi, rappel à créer"

    history = query(
        "SELECT count(*) AS total, max(sent_on) AS last_sent FROM notification_log "
        "WHERE reminder_id = %s",
        (reminder["id"],),
        fetch="one",
    )
    if history["total"] == 0:
        return True, "premier envoi"
    if history["total"] > policy["max_resends"]:
        return False, f"{policy['max_resends']} renvois atteints"

    candidates = [("dernier envoi", history["last_sent"])]
    done = ctx.last_care.get(action)
    if done:
        candidates.append(("dernier soin", done))
    label, reference = max(
        ((name, day) for name, day in candidates if day), key=lambda pair: pair[1]
    )

    waited = (ctx.today - reference).days
    remaining = policy["delay_days"] - waited
    if remaining <= 0:
        return True, f"renvoi {history['total'] + 1}, {label} le {reference:%d/%m/%Y}"
    return False, f"renvoi dans {remaining} jour(s), {label} le {reference:%d/%m/%Y}"


def _close_stale_runs() -> None:
    """Marks as aborted any run still 'running' well past its plausible length.

    There is no watchdog: the daily batch is the only thing that ever runs, so
    the sweep happens at the start of the next one. A row left 'running' means
    the process died before it could report back.
    """
    query(
        "UPDATE batch_run SET status = 'aborted', finished_at = now() "
        "WHERE status = 'running' AND started_at < now() - make_interval(mins => %s)",
        (STALE_RUN_MINUTES,),
    )


def run() -> None:
    _close_stale_runs()

    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("INSERT INTO batch_run DEFAULT VALUES RETURNING id, started_at")
            batch = cur.fetchone()
    log.info("Batch %s démarré", batch["id"])

    counters = {"sites_ok": 0, "sites_failed": 0, "reminders_new": 0, "sent": 0, "send_failed": 0}
    failure = None

    try:
        # 1 — weather, one call per open site
        counters["sites_ok"], counters["sites_failed"] = weather.collect(batch["id"])

        # 2 — reminders, one plant at a time so a bad one does not stop the rest
        contexts = {}
        for plant_id in _open_plants():
            try:
                counters["reminders_new"] += len(generate(plant_id, batch["id"]))
                contexts[plant_id] = context(plant_id)
            except Exception:
                log.exception("Génération impossible pour la plante %s", plant_id)

        # 3 — notifications, guarded by the resend policy and the unique index
        today = date.today()  # DETTE : UTC, voir le commentaire sur _due_reminders
        for reminder in _due_reminders(today):
            ctx = contexts.get(reminder["plant_id"])
            if ctx is None:
                continue
            try:
                allowed, _ = send_decision(reminder["plant_id"], reminder["action"], ctx)
                if not allowed:
                    continue
                title, body = message(ctx, reminder["action"])
                send(title, body)
                query(
                    "INSERT INTO notification_log "
                    "(plant_id, action, reminder_id, batch_run_id, sent_on, payload) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (plant_id, action, sent_on) DO NOTHING",
                    (
                        reminder["plant_id"],
                        reminder["action"],
                        reminder["id"],
                        batch["id"],
                        ctx.today,
                        json.dumps(ctx.payload(reminder["action"])),
                    ),
                )
                counters["sent"] += 1
            except Exception:
                log.exception("Envoi impossible pour la plante %s", reminder["plant_id"])
                counters["send_failed"] += 1

    except Exception as error:  # noqa: BLE001 — recorded, never swallowed silently
        failure = str(error)
        log.exception("Batch interrompu")

    # The status is written, not derived: 'running' stays only on a run that
    # never reported back, which is the signal that it died mid-flight.
    # A run that wrote no reading at all is not a success either — no open
    # site, or every site failing, both leave the engine without weather.
    status = (
        "failed"
        if failure
        or counters["send_failed"]
        or counters["sites_failed"]
        or not counters["sites_ok"]
        else "ok"
    )
    assignments = ", ".join(f"{name} = %s" for name in counters)
    query(
        f"UPDATE batch_run SET finished_at = now(), status = %s, {assignments}, "
        "error = %s WHERE id = %s",
        (status,) + tuple(counters.values()) + (failure, batch["id"]),
    )
    log.info(
        "Batch %s terminé : %s site(s), %s rappel(s), %s envoi(s), %s échec(s)",
        batch["id"],
        counters["sites_ok"],
        counters["reminders_new"],
        counters["sent"],
        counters["send_failed"],
    )

    # The row is written first, then the process fails: GitHub Actions must go
    # red on a bad run, otherwise a silent failure looks like a success
    if failure or counters["send_failed"] or counters["sites_failed"]:
        raise SystemExit(1)


def preview() -> None:
    """What the batch would do, computed the same way, written nowhere.

    Every action is listed, due or not, with the exact reason — an overdue
    repotting out of season must read as late, not merely as out of window.
    """
    for plant_id in _open_plants():
        ctx = context(plant_id)
        if ctx is None:
            continue

        # ctx.today comes from the site timezone, never date.today(): the preview
        # and the batch must agree on which day it is
        print(f"=== {ctx.plant_name} — {ctx.species_name}   ({ctx.today:%d/%m/%Y})")

        # Conditions, not tasks: shown once per plant, above the actions
        if ctx.exposure_alert:
            print(f"  {'lumière':14} {ctx.exposure_alert}")
        if ctx.humidity_alert:
            print(f"  {'humidité':14} {ctx.humidity_alert}")
        for alert in ctx.placement_alerts:
            print(f"  {'placement':14} {alert}")

        for verdict in assess_all(ctx):
            label = LABELS[verdict.action]
            if not verdict.is_due:
                print(f"  {label:14} {verdict.reason}")
                continue

            allowed, why = send_decision(plant_id, verdict.action, ctx)
            mark = "ENVOI" if allowed else "retenu"
            print(f"  {label:14} échue le {verdict.due_on:%d/%m/%Y} — {mark} : {why}")
            if allowed:
                title, body = message(ctx, verdict.action)
                for line in [title, *body.split("\n")]:
                    print(f"                 {line}")
        print()


LABELS = {"watering": "arrosage", "fertilizing": "fertilisation", "repotting": "rempotage"}


if __name__ == "__main__":
    import sys

    preview() if "--preview" in sys.argv else run()
