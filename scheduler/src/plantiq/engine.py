# scheduler/src/plantiq/engine.py

import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from plantiq.core.database import engine as db_engine
from plantiq.core.logging import get_logger
from plantiq.notify import send
from plantiq.weather import get_weather

log = get_logger(__name__)
TZ = ZoneInfo("Europe/Brussels")
SUMMER_MONTHS = range(4, 10)  # April–September inclusive

# Fraction of pot volume to deliver per watering, by water need level
_WATERING_COEFFICIENTS = {"light": 0.025, "moderate": 0.04, "heavy": 0.06}

_WATERING_MODE_LABELS = {
    "soil_only": "sur la terre uniquement",
    "leaves":    "directement sur les feuilles",
    "misting":   "par brumisation",
    "mixed":     "sur la terre + brumisation",
}


# --- helpers

def _active_issue(health: dict | None) -> str | None:
    # A resolved health issue must stop affecting frequency/quantity — only "resolved_at" marks that
    if not health or health.get("resolved_at"):
        return None
    return health.get("issue_type")


def has_mold(container: dict | None) -> bool:
    if not container:
        return False
    issues = (container.get("soil_issues") or "").lower()
    return container.get("soil_condition") == "moldy" or "mold" in issues


def get_watering_quantity(profile: dict, container: dict | None) -> int:
    if profile.get("watering_quantity_ml"):
        return profile["watering_quantity_ml"]
    diameter = container.get("pot_diameter_cm") if container else None
    height   = container.get("pot_height_cm") if container else None
    if not diameter or not height:
        return 300
    volume_ml = math.pi * (diameter / 2) ** 2 * height
    qty = volume_ml * _WATERING_COEFFICIENTS.get(profile.get("watering_amount", "moderate"), 0.04)
    return max(100, round(qty / 50) * 50)


def apply_quantity_modifiers(qty: int, weather: dict | None, container: dict | None, health: dict | None) -> int:
    if weather and (weather.get("temperature_max") or 0) > 30:
        qty = int(qty * 1.20)
    if container and not container.get("has_drainage", True):
        qty = int(qty * 0.50)
    if _active_issue(health) == "overwatering":
        qty = int(qty * 0.50)
    if container and container.get("pot_type") == "terracotta":
        qty = int(qty * 1.10)
    return max(50, round(qty / 50) * 50)


def _days_since(done_at, tz: ZoneInfo, today: date) -> int:
    if done_at is None:
        return 999
    ref = done_at.astimezone(tz).date() if hasattr(done_at, "astimezone") else done_at
    return (today - ref).days


def _recently_notified(last: dict | None, days: int, today: date, tz: ZoneInfo) -> bool:
    if not last:
        return False
    sent_at = last.get("sent_at")
    if not sent_at:
        return False
    ref = sent_at.astimezone(tz).date() if hasattr(sent_at, "astimezone") else sent_at
    return (today - ref).days < days


def _season(today: date) -> str:
    return "summer" if today.month in SUMMER_MONTHS else "winter"


# --- persistence helpers

def _store_weather(conn, location_id: str, lat: float, lon: float, today: date) -> dict | None:
    try:
        w = get_weather(lat, lon)
    except Exception:
        log.exception("OWM failed for location %s", location_id)
        return None

    conn.execute(text("""
        INSERT INTO weather_logs
               (location_id, date, temperature_min, temperature_max,
                humidity, condition, wind_speed)
        VALUES (:loc_id, :date, :temp_min, :temp_max,
                :humidity, CAST(:condition AS weather_condition), :wind_speed)
        ON CONFLICT (location_id, date) DO UPDATE SET
            temperature_min = EXCLUDED.temperature_min,
            temperature_max = EXCLUDED.temperature_max,
            humidity        = EXCLUDED.humidity,
            condition       = EXCLUDED.condition,
            wind_speed      = EXCLUDED.wind_speed,
            fetched_at      = NOW()
    """), {
        "loc_id":   location_id,
        "date":     today,
        "temp_min": w["temperature_min"],
        "temp_max": w["temperature_max"],
        "humidity": w["humidity"],
        "condition": w["condition"],
        "wind_speed": w["wind_speed"],
    })
    return w


def _log_notification(conn, plant_id: str, notif_type: str, message: str, triggered_by: str) -> None:
    conn.execute(text("""
        INSERT INTO notifications_log (plant_id, type, message, triggered_by)
        VALUES (:plant_id, CAST(:type AS notif_type), :message, CAST(:triggered_by AS notif_trigger))
    """), {"plant_id": plant_id, "type": notif_type, "message": message, "triggered_by": triggered_by})


def _notify(conn, plant: dict, notif_type: str, title: str, body: str, triggered_by: str) -> None:
    _log_notification(conn, str(plant["id"]), notif_type, body, triggered_by)
    send(title, body)


# --- rules

def _rule_weather_warning(conn, plant, profile, pl, weather, health, last_notifs, snoozes, today, tz):
    if "warning" in snoozes:
        return
    if health and health.get("status") == "dying":
        return
    if not weather:
        return
    if _recently_notified(last_notifs.get("warning"), 1, today, tz):
        return

    temp_max   = weather.get("temperature_max") or 0
    temp_min   = weather.get("temperature_min") or 0
    is_indoor  = pl.get("indoor", True) if pl else True
    near_ac    = pl.get("near_ac", False) if pl else False
    temp_max_c  = profile.get("temp_max_c") if profile else None
    temp_min_c  = profile.get("temp_min_c") if profile else None
    issue_type  = _active_issue(health)

    lines = []
    if temp_max_c and temp_max > temp_max_c:
        if issue_type == "overwatering":
            lines.append(f"{temp_max:.1f}°C dépasse le seuil de {temp_max_c:.0f}°C. Ne pas arroser - surveiller l'humidité du substrat.")
        else:
            lines.append(f"{temp_max:.1f}°C dépasse le seuil de {temp_max_c:.0f}°C. Arrosage prioritaire.")
    if temp_min_c and temp_min < temp_min_c:
        lines.append(f"{temp_min:.0f}°C sous {temp_min_c:.0f}°C. Protéger la plante.")
    if temp_max > 35 and is_indoor and not near_ac:
        lines.append(f"Chaleur {temp_max:.0f}°C en intérieur sans climatisation.")

    if not lines:
        return

    _notify(conn, plant, "warning", f"Alerte - {plant['name']}", "\n".join(lines), "weather")


def _rule_health_check(conn, plant, health, last_notifs, snoozes, today, tz):
    if "health_check" in snoozes:
        return
    if not health or health.get("status") in ("healthy", None):
        return

    status = health.get("status")
    dedup  = 3 if status == "dying" else 7 if status in ("sick", "recovering") else 15

    if _recently_notified(last_notifs.get("health_check"), dedup, today, tz):
        return

    lines = [
        f"Statut : {status}.",
        f"Problème : {health.get('issue_type', 'none')}.",
        f"Traitement : {health.get('treating ') or 'aucun'}.",
    ]
    if status == "dying":
        lines.append("ALERTE - état critique. Intervention immédiate requise.")

    _notify(conn, plant, "health_check", f"Sante - {plant['name']}", "\n".join(lines), "health_status")


def _rule_repotting(conn, plant, profile, container, health, last_notifs, snoozes, today, tz):
    if "repotting" in snoozes:
        return
    if health and health.get("status") == "dying":
        if not (container and container.get("repotting_urgent")):
            return
    if _recently_notified(last_notifs.get("repotting"), 30, today, tz):
        return

    lines = []
    triggered = False

    # A - Urgent
    if container and container.get("repotting_urgent"):
        triggered = True
        notes = container.get("repotting_notes") or ""
        lines.append(f"Rempotage urgent. {notes}".strip())

    # B - Calendar
    if not triggered and profile:
        freq_months = profile.get("repotting_frequency_months")
        if freq_months:
            last_repotted = container.get("last_repotted") if container else None
            if last_repotted:
                months_since = (today - last_repotted).days / 30
                if months_since >= freq_months:
                    triggered = True
                    lines.append(f"Dernier rempotage il y a {int(months_since)} mois. Fréquence : {freq_months} mois.")
            else:
                triggered = True
                lines.append(f"Date de rempotage inconnue. Fréquence : {freq_months} mois.")

    # C - Soil condition
    if container:
        bad_soil = container.get("soil_condition") in ("exhausted", "moldy", "compacted", "waterlogged")
        mold = has_mold(container)
        if bad_soil or mold:
            triggered = True
            if bad_soil:
                lines.append(f"Substrat : {container.get('soil_condition')}.")
            if mold:
                lines.append("Moisissures détectées dans le substrat.")

    if not triggered:
        return

    if health and health.get("status") == "sick":
        _notify(conn, plant, "warning", f"Rempotage - {plant['name']}",
                "Rempotage recommandé mais plante malade - attendre stabilisation.", "health_status")
        return

    _notify(conn, plant, "repotting", f"Rempotage - {plant['name']}", "\n".join(lines), "schedule")


def _rule_watering(conn, plant, profile, pl, container, accessories, health, weather, care_logs, last_notifs, snoozes, today, tz):
    if "watering" in snoozes:
        return
    if health and health.get("status") in ("dying", "burned"):
        return
    if container and container.get("soil_condition") == "waterlogged":
        return  # Terre saturée — pas d'arrosage

    freq_base = profile.get(f"watering_frequency_days_{_season(today)}")
    if not freq_base:
        return

    last_log = care_logs.get("watering")
    jours    = _days_since(last_log.get("done_at") if last_log else None, tz, today)

    freq       = freq_base
    is_indoor  = pl.get("indoor", True) if pl else True
    temp_max   = (weather or {}).get("temperature_max") or 0
    humidity   = (weather or {}).get("humidity") or 0
    condition  = (weather or {}).get("condition") or ""

    # Weather modifiers
    if weather:
        if temp_max > 35:
            freq -= 5
        elif temp_max > 30:
            freq -= 3
        if temp_max < 10:
            freq += 3
        if not is_indoor:
            if humidity > 80:
                freq += 2
            if condition == "rainy":
                freq += 2
            if condition == "stormy":
                freq += 3

    # Environment modifiers
    if pl:
        if pl.get("shade"):
            freq += 3
        if pl.get("near_ac"):
            freq -= 1
        if pl.get("near_heating"):
            freq -= 1

    # Pot modifiers
    if container:
        if container.get("pot_type") in ("terracotta", "fabric"):
            freq -= 2
        if not container.get("has_drainage", True):
            freq += 2

    # Cachepot modifiers
    cachepot = next((a for a in accessories if a.get("type") == "cachepot"), None)
    if cachepot:
        freq += 1
        if not cachepot.get("has_clay_pebbles"):
            freq += 1

    # Health modifiers
    if health:
        issue  = _active_issue(health)
        status = health.get("status")
        if issue == "overwatering":
            freq += 5
        elif issue == "underwatering":
            freq -= 3
        if status == "dormant":
            freq = freq * 2

    freq = max(1, int(freq))

    if jours < freq:
        return
    if _recently_notified(last_notifs.get("watering"), freq, today, tz):
        return

    qty     = get_watering_quantity(profile, container)
    qty_eff = apply_quantity_modifiers(qty, weather, container, health)
    if health and health.get("status") == "dormant":
        qty_eff = max(50, round(qty_eff * 0.5 / 50) * 50)
    mode    = profile.get("watering_mode") or "soil_only"
    instructions = profile.get("watering_instructions") or ""

    city = plant.get("city", "")
    weather_line = f"{city} : {temp_max:.0f}°C, {condition}." if weather else ""

    lines = [
        f"Dernier arrosage il y a {jours} jours.",
        weather_line,
        "",
        f"Comment : {_WATERING_MODE_LABELS.get(mode, 'sur la terre')} - {qty_eff} ml.",
    ]
    if instructions:
        lines.append(instructions)
    if container and not container.get("has_drainage", True):
        lines.append("Pot non percé - quantité réduite obligatoire.")
    if temp_max > 30:
        lines.append("Chaleur importante - arrosage prioritaire.")
    if condition == "rainy" and not is_indoor:
        lines.append("Pluie en cours - quantité allégée.")
    if _active_issue(health) == "overwatering":
        lines.append("Surrosage passé - laisser sécher entre les arrosages.")
    if pl and pl.get("shade"):
        lines.append("Plante ombragée - vérifier le substrat avant d'arroser.")

    body = "\n".join(line for line in lines if line)
    _notify(conn, plant, "watering", f"Arrosage - {plant['name']}", body, "schedule")

    conn.execute(text("""
        INSERT INTO care_logs (plant_id, action, quantity_ml, note)
        VALUES (:plant_id, CAST(:action AS care_action), :qty_ml, :note)
    """), {"plant_id": str(plant["id"]), "action": "watering", "qty_ml": qty_eff, "note": "auto-logged by engine"})


def _rule_misting(conn, plant, profile, pl, container, health, weather, care_logs, last_notifs, snoozes, today, tz):
    if "misting" in snoozes:
        return
    if profile.get("humidity_level") != "high":
        return
    if _active_issue(health) == "overwatering":
        return
    if has_mold(container):
        return
    if not pl:
        return

    humidity  = (weather or {}).get("humidity") or 100
    near_ac   = pl.get("near_ac", False)
    near_heat = pl.get("near_heating", False)

    if not (humidity < 50 or near_ac or near_heat):
        return

    last_log = care_logs.get("misting")
    jours    = _days_since(last_log.get("done_at") if last_log else None, tz, today)

    if jours <= 3:
        return
    if _recently_notified(last_notifs.get("misting"), 3, today, tz):
        return

    lines = [f"Humidité ambiante : {humidity:.0f}%."]
    if near_ac:
        lines.append("Climatisation active - brumisation recommandée.")
    if near_heat:
        lines.append("Chauffage actif - brumisation recommandée.")

    _notify(conn, plant, "misting", f"Brumisation - {plant['name']}", "\n".join(lines), "schedule")


def _rule_fertilizing(conn, plant, profile, container, health, care_logs, last_notifs, snoozes, today, tz):
    if "fertilizing" in snoozes:
        return
    if today.month not in SUMMER_MONTHS:
        return
    if container and (
        container.get("soil_condition") in ("exhausted", "waterlogged")
        or has_mold(container)
    ):
        return
    if health and health.get("status") in ("sick", "dying", "dormant", "recovering"):
        return
    if container and container.get("last_repotted"):
        if (today - container["last_repotted"]).days < 60:
            return

    freq = profile.get("fertilizing_frequency_days")
    if not freq:
        return

    last_log = care_logs.get("fertilizing")
    jours    = _days_since(last_log.get("done_at") if last_log else None, tz, today)

    if jours < freq:
        return
    if _recently_notified(last_notifs.get("fertilizing"), freq, today, tz):
        return

    lines = [
        f"Dernière fertilisation il y a {jours} jours.",
        f"Fréquence recommandée : tous les {freq} jours (mars-septembre).",
    ]
    if container and container.get("soil_condition") == "compacted":
        lines.append("Substrat compacté - fertiliser avec une dose réduite de moitié.")
    _notify(conn, plant, "fertilizing", f"Fertilisation - {plant['name']}", "\n".join(lines), "schedule")


# --- main

def run_engine() -> None:
    today = datetime.now(TZ).date()

    with db_engine.connect() as conn:
        plants = conn.execute(text("""
            SELECT p.id, p.name, p.species,
                   l.id as location_id, l.city, l.latitude, l.longitude
            FROM plants p
            JOIN locations l ON l.id = p.location_id
        """)).mappings().fetchall()

        log.info("Processing %d plants", len(plants))
        if not plants:
            return

        # Fetch and persist weather once per unique location
        weather_by_location: dict[str, dict | None] = {}
        for plant in plants:
            loc_id = str(plant["location_id"])
            if loc_id not in weather_by_location:
                weather_by_location[loc_id] = _store_weather(
                    conn, loc_id, plant["latitude"], plant["longitude"], today
                )
        conn.commit()

        # Batch load all satellite data
        ids = [str(p["id"]) for p in plants]

        profiles = {str(r["plant_id"]): dict(r) for r in conn.execute(
            text("SELECT * FROM plant_profile WHERE plant_id = ANY(:ids)"),
            {"ids": ids},
        ).mappings().fetchall()}

        plocations = {str(r["plant_id"]): dict(r) for r in conn.execute(
            text("SELECT * FROM plant_location WHERE plant_id = ANY(:ids)"),
            {"ids": ids},
        ).mappings().fetchall()}

        containers = {str(r["plant_id"]): dict(r) for r in conn.execute(
            text("SELECT * FROM plant_container WHERE plant_id = ANY(:ids)"),
            {"ids": ids},
        ).mappings().fetchall()}

        accessories_by_plant: dict[str, list] = {}
        for row in conn.execute(
            text("SELECT * FROM plant_accessories WHERE plant_id = ANY(:ids)"),
            {"ids": ids},
        ).mappings().fetchall():
            accessories_by_plant.setdefault(str(row["plant_id"]), []).append(dict(row))

        health_by_plant = {str(r["plant_id"]): dict(r) for r in conn.execute(text("""
            SELECT DISTINCT ON (plant_id) *
            FROM plant_health
            WHERE plant_id = ANY(:ids)
            ORDER BY plant_id, observed_at DESC NULLS LAST
        """), {"ids": ids}).mappings().fetchall()}

        care_by_plant: dict[str, dict] = {}
        for row in conn.execute(text("""
            SELECT DISTINCT ON (plant_id, action) *
            FROM care_logs
            WHERE plant_id = ANY(:ids)
            ORDER BY plant_id, action, done_at DESC NULLS LAST
        """), {"ids": ids}).mappings().fetchall():
            care_by_plant.setdefault(str(row["plant_id"]), {})[row["action"]] = dict(row)

        notifs_by_plant: dict[str, dict] = {}
        for row in conn.execute(text("""
            SELECT DISTINCT ON (plant_id, type) *
            FROM notifications_log
            WHERE plant_id = ANY(:ids)
            ORDER BY plant_id, type, sent_at DESC NULLS LAST
        """), {"ids": ids}).mappings().fetchall():
            notifs_by_plant.setdefault(str(row["plant_id"]), {})[row["type"]] = dict(row)

        snoozes_by_plant: dict[str, set] = {}
        for row in conn.execute(text("""
            SELECT plant_id, notif_type FROM notification_snooze
            WHERE plant_id = ANY(:ids)
            AND done = false
            AND (snoozed_until IS NULL OR snoozed_until >= :today)
        """), {"ids": ids, "today": today}).mappings().fetchall():
            snoozes_by_plant.setdefault(str(row["plant_id"]), set()).add(str(row["notif_type"]))

        # Evaluate rules for each plant in priority order
        for plant in plants:
            pid     = str(plant["id"])
            profile = profiles.get(pid)

            if not profile:
                log.warning("No profile for plant %s — skipping", plant["name"])
                continue

            p           = dict(plant)
            pl          = plocations.get(pid)
            container   = containers.get(pid)
            accessories = accessories_by_plant.get(pid, [])
            health      = health_by_plant.get(pid)
            care_logs   = care_by_plant.get(pid, {})
            last_notifs = notifs_by_plant.get(pid, {})
            weather     = weather_by_location.get(str(plant["location_id"]))

            snoozes = snoozes_by_plant.get(pid, set())
            # Each rule commits independently — a failure in one rule does not roll back a prior notification
            for rule in [
                lambda: _rule_weather_warning(conn, p, profile, pl, weather, health, last_notifs, snoozes, today, TZ),
                lambda: _rule_health_check(conn, p, health, last_notifs, snoozes, today, TZ),
                lambda: _rule_repotting(conn, p, profile, container, health, last_notifs, snoozes, today, TZ),
                lambda: _rule_watering(conn, p, profile, pl, container, accessories, health, weather, care_logs, last_notifs, snoozes, today, TZ),
                lambda: _rule_misting(conn, p, profile, pl, container, health, weather, care_logs, last_notifs, snoozes, today, TZ),
                lambda: _rule_fertilizing(conn, p, profile, container, health, care_logs, last_notifs, snoozes, today, TZ),
            ]:
                try:
                    rule()
                    conn.commit()
                except Exception as e:
                    log.error("Engine error for plant %s: %s", plant["name"], e)
                    conn.rollback()
