# app/src/plantiq/engine/rules.py

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from plantiq.core.database import query
from plantiq.engine.climate import indoor_humidity, indoor_temperature
from plantiq.engine.geometry import wall_lengths
from plantiq.engine.light import LEVEL_ORDER, nearest_of_type, position_in_room
from plantiq.engine.light import exposure as compute_exposure

SEASON_BY_MONTH = {
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
    12: "winter", 1: "winter", 2: "winter",
}

# Seasons change on the first of March, June, September and December. A plant
# does not notice midnight: the base interval is blended linearly over a window
# straddling each boundary, so 31 August and 1 September differ by hours of
# interpolation rather than by a jump of eight days.
SEASON_BOUNDARIES = [
    (3, "winter", "spring"),
    (6, "spring", "summer"),
    (9, "summer", "autumn"),
    (12, "autumn", "winter"),
]
TRANSITION_DAYS = 15

# The product of the five factors is clipped: a pile-up of adjustments must not
# produce an absurd interval. This replaces the per-species sensitivity we dropped.
FACTOR_FLOOR, FACTOR_CEILING = 0.70, 1.40

HEATING_MONTHS = {10, 11, 12, 1, 2, 3, 4}

# Past this, an out-of-window action is notified anyway, as something to plan.
# Without it a repotting overdue since 2024 would stay silent until March 2027.
OVERDUE_ESCALATION_DAYS = 365

# Fresh substrate already carries fertiliser: adding more burns the roots.
# A NULL potted_on blocks nothing — an unknown date is not a recent one.
REPOTTING_FERTILIZING_GAP_DAYS = 60

# A resting or failing plant is not taking up nutrients. Watering is left alone:
# a plant in trouble still drinks, and stopping that would make things worse.
FERTILIZING_BLOCKED_BY = {
    "dormant": "en dormance, la fertilisation attend la reprise",
    "dying": "en train de dépérir, l'engrais aggraverait le stress racinaire",
}

# A container that holds its water keeps the substrate wet: the interval
# lengthens instead of shortening. The outer shell decides — a cachepot
# without a hole overrides a pierced pot sitting inside it.
NO_DRAINAGE_FACTOR = 1.15


@dataclass
class Context:
    """Everything the rules need. Missing data degrades to a neutral factor."""

    plant_id: int
    plant_name: str
    species_name: str
    site_id: int | None = None
    timezone: str = "Europe/Brussels"
    today: date | None = None
    room_name: str | None = None
    city: str | None = None

    season: str = "summer"
    season_intervals: dict = field(default_factory=dict)
    base_interval: float | None = None
    watering_ml_per_litre: int | None = None
    volume_l: float | None = None
    volume_ml: int | None = None
    material_is_porous: bool | None = None
    cachepot_name: str | None = None
    drains: bool | None = None

    environment: str | None = None
    exposure: object | None = None
    # Measured light against the range the species tolerates. None when in range.
    exposure_alert: str | None = None
    position: str | None = None
    radiator_m: float | None = None
    weather: dict | None = None
    # What the plant actually experiences: converted indoors, raw outdoors
    temp_c: float | None = None
    humidity_pct: float | None = None
    # 0 when today's reading exists, higher when falling back on an older one
    weather_age_days: int | None = None

    last_care: dict = field(default_factory=dict)
    last_potted_on: date | None = None
    # Most recent plant_health row: there is no status column on plant
    health: dict | None = None

    factors: dict = field(default_factory=dict)
    interval: int | None = None
    species: dict = field(default_factory=dict)
    material_label: str | None = None

    def payload(self) -> dict:
        """Inputs of the computation, stored with the notification."""
        return {
            "season": self.season,
            # Interpolated across a season change, hence a decimal
            "base_interval": (
                round(self.base_interval, 2) if self.base_interval is not None else None
            ),
            "season_weights": {
                season: round(weight, 3) for season, weight in season_blend(self.today)
            },
            "factors": {name: round(value, 3) for name, value in self.factors.items()},
            "interval": self.interval,
            "volume_ml": self.volume_ml,
            "exposure": (
                {
                    "intensity": round(self.exposure.intensity, 3),
                    "level": self.exposure.level,
                    "distance_m": (
                        round(self.exposure.distance_m, 2) if self.exposure.distance_m else None
                    ),
                    "cardinal": self.exposure.cardinal,
                    "alert": self.exposure_alert,
                }
                if self.exposure
                else None
            ),
            "health": (
                {
                    "status": self.health["status"],
                    "noted_on": self.health["noted_on"].isoformat(),
                }
                if self.health
                else None
            ),
            "container": {
                "material": self.material_label,
                "porous": self.material_is_porous,
                "cachepot": self.cachepot_name,
                "drains": self.drains,
            },
            "position": self.position,
            "radiator_m": round(self.radiator_m, 2) if self.radiator_m else None,
            "weather": (
                {
                    "temp_c": float(self.weather["temp_c"]) if self.weather["temp_c"] else None,
                    "humidity_pct": (
                        float(self.weather["humidity_pct"])
                        if self.weather["humidity_pct"]
                        else None
                    ),
                    "cloud_pct": self.weather["cloud_pct"],
                    "observed_on": self.weather["observed_on"].isoformat(),
                    "age_days": self.weather_age_days,
                }
                if self.weather
                else None
            ),
            "environment": self.environment,
            # The pair the factors were actually computed from
            "effective": {
                "temp_c": round(self.temp_c, 1) if self.temp_c is not None else None,
                "humidity_pct": (
                    round(self.humidity_pct, 1) if self.humidity_pct is not None else None
                ),
                "converted": self.environment == "indoor" and self.weather is not None,
            },
        }


# --- factors, each neutral at 1.00


def factor_porous(is_porous: bool | None, has_cachepot: bool = False) -> float:
    # Terracotta breathes through its walls — unless it sits inside a cachepot,
    # which seals those walls off and cancels the effect entirely
    if has_cachepot:
        return 1.00
    return 0.85 if is_porous else 1.00


def factor_drainage(drains: bool | None) -> float:
    """Neutral when unknown: a missing value is not a blocked one."""
    if drains is None:
        return 1.00
    return 1.00 if drains else NO_DRAINAGE_FACTOR


def factor_exposure(exposure) -> float:
    # Unknown exposure stays neutral: a dark room is not the same as no data
    if exposure is None:
        return 1.00
    return 1.15 - 0.25 * min(exposure.intensity, 2)


def factor_temperature(temp_c: float | None) -> float:
    if temp_c is None:
        return 1.00
    return max(0.85, 1 - 0.015 * max(0.0, temp_c - 25))


def factor_humidity(humidity_pct: float | None) -> float:
    if humidity_pct is None:
        return 1.00
    return min(1.10, max(0.90, 1 + 0.004 * (humidity_pct - 60)))


def factor_radiator(distance_m: float | None, month: int) -> float:
    if distance_m is None or month not in HEATING_MONTHS:
        return 1.00
    if distance_m < 1:
        return 0.80
    return 0.90 if distance_m <= 2 else 1.00


# --- diagnostics: measured conditions against what the species tolerates

EXPOSURE_LABELS = {
    "low": "faible",
    "indirect": "indirecte",
    "bright_indirect": "vive indirecte",
    "direct": "directe",
}


def exposure_alert(exposure, exposure_min: str | None, exposure_max: str | None) -> str | None:
    """Names the gap when the measured light falls outside the tolerated range.

    None means either "in range" or "nothing to say": no window, none visible, or no
    calibration to turn plan units into metres. Silence is never an all-clear here.

    The temperature half of the same check is deliberately left out. indoor_temperature
    clamps a room to [20, 28] °C, so a species minimum of 18 °C can never be crossed
    indoors — the comparison would be structurally silent, which reads as reassurance
    and is worse than no comparison. Reinstating it means revisiting that floor first:
    see docs/test-batch-2026-08-19.md, anomaly 5.6.
    """
    if exposure is None or not exposure.visible or not exposure_min or not exposure_max:
        return None

    measured = LEVEL_ORDER.index(exposure.level)
    label = EXPOSURE_LABELS[exposure.level]
    if measured < LEVEL_ORDER.index(exposure_min):
        return (
            f"Lumière insuffisante : exposition {label}, "
            f"l'espèce demande au moins {EXPOSURE_LABELS[exposure_min]}."
        )
    if measured > LEVEL_ORDER.index(exposure_max):
        return (
            f"Lumière excessive : exposition {label}, "
            f"l'espèce tolère au plus {EXPOSURE_LABELS[exposure_max]}."
        )
    return None


def season_blend(today: date) -> list[tuple[str, float]]:
    """Season weights for a date, blended across the transition windows.

    Outside a window a single season carries all the weight. Inside one, the
    two neighbours share it linearly: half each on the boundary itself.
    """
    nearest = None
    for year in (today.year - 1, today.year, today.year + 1):
        for month, before, after in SEASON_BOUNDARIES:
            boundary = date(year, month, 1)
            delta = (today - boundary).days
            if nearest is None or abs(delta) < abs(nearest[0]):
                nearest = (delta, before, after)

    delta, before, after = nearest
    if abs(delta) > TRANSITION_DAYS:
        return [(SEASON_BY_MONTH[today.month], 1.0)]

    weight_after = (delta + TRANSITION_DAYS) / (2 * TRANSITION_DAYS)
    return [(before, 1 - weight_after), (after, weight_after)]


def blended_interval(today: date, intervals: dict[str, int]) -> float | None:
    """Base interval for the day, interpolated across a season change."""
    weights = [(season, weight) for season, weight in season_blend(today) if season in intervals]
    total = sum(weight for _, weight in weights)
    if not total:
        return None
    return sum(intervals[season] * weight for season, weight in weights) / total


def in_month_window(month: int, start: int | None, end: int | None) -> bool:
    """A window whose start is after its end wraps around the new year."""
    if start is None or end is None:
        return True
    return start <= month <= end if start <= end else month >= start or month <= end


# --- context


def context(plant_id: int) -> Context | None:
    plant = query(
        """
        SELECT p.id, p.name, sp.scientific_name, sp.watering_ml_per_litre,
               sp.exposure_min, sp.exposure_max,
               sp.fertilizing_interval_days, sp.fertilizing_month_start, sp.fertilizing_month_end,
               sp.repotting_interval_months, sp.repotting_month_start, sp.repotting_month_end,
               sp.id AS species_id
        FROM plant p JOIN species sp ON sp.id = p.species_id
        WHERE p.id = %s AND p.closed_at IS NULL
        """,
        (plant_id,),
        fetch="one",
    )
    if plant is None:
        return None

    ctx = Context(
        plant_id=plant["id"],
        plant_name=plant["name"],
        species_name=plant["scientific_name"],
        watering_ml_per_litre=plant["watering_ml_per_litre"],
    )
    ctx.species = plant

    placement = query(
        """
        SELECT pl.x, pl.y, v.id AS version_id, v.north_angle, v.environment,
               v.scale_wall_index, v.scale_cm, r.name AS room_name,
               s.id AS site_id, s.city, s.timezone
        FROM plant_placement pl
        JOIN room_version v ON v.id = pl.room_version_id
        JOIN room r ON r.id = v.room_id
        JOIN site s ON s.id = r.site_id
        WHERE pl.plant_id = %s AND pl.closed_at IS NULL
        """,
        (plant_id,),
        fetch="one",
    )
    if placement:
        ctx.site_id = placement["site_id"]
        ctx.timezone = placement["timezone"]
        ctx.room_name = placement["room_name"]
        ctx.city = placement["city"]
        ctx.environment = placement["environment"]

    ctx.today = datetime.now(ZoneInfo(ctx.timezone)).date()
    ctx.season = SEASON_BY_MONTH[ctx.today.month]

    ctx.season_intervals = {
        row["season"]: row["interval_days"]
        for row in query(
            "SELECT season, interval_days FROM species_watering WHERE species_id = %s",
            (plant["species_id"],),
            fetch="all",
        )
    }
    ctx.base_interval = blended_interval(ctx.today, ctx.season_intervals)

    attached = {
        row["equipment_type"]: row
        for row in query(
            """
            SELECT pe.equipment_type, pe.attached_on, e.name, e.volume_l, e.has_drainage,
                   m.is_porous, m.label AS material_label
            FROM plant_equipment pe JOIN equipment e ON e.id = pe.equipment_id
            LEFT JOIN material m ON m.id = e.material_id
            WHERE pe.plant_id = %s AND pe.closed_at IS NULL
            """,
            (plant_id,),
            fetch="all",
        )
    }
    pot, cachepot = attached.get("pot"), attached.get("cachepot")

    ctx.material_is_porous = pot["is_porous"] if pot else None
    ctx.material_label = pot["material_label"] if pot else None
    ctx.cachepot_name = cachepot["name"] if cachepot else None
    # The outer shell governs drainage: the cachepot when there is one
    ctx.drains = (cachepot or pot or {}).get("has_drainage")

    if pot and pot["volume_l"]:
        ctx.volume_l = float(pot["volume_l"])
        if ctx.watering_ml_per_litre:
            ctx.volume_ml = round(ctx.volume_l * ctx.watering_ml_per_litre)

    # Geometry: needs a placement, a polygon and a calibration to mean anything
    if placement:
        vertices = [
            (float(v["x"]), float(v["y"]))
            for v in query(
                "SELECT x, y FROM room_vertex WHERE room_version_id = %s ORDER BY position",
                (placement["version_id"],),
                fetch="all",
            )
        ]
        elements = [
            {
                "wall_index": e["wall_index"],
                "type": e["type"],
                "t_start": float(e["t_start"]),
                "t_end": float(e["t_end"]),
            }
            for e in query(
                "SELECT wall_index, type, t_start, t_end FROM wall_element "
                "WHERE room_version_id = %s AND closed_at IS NULL",
                (placement["version_id"],),
                fetch="all",
            )
        ]
        units_per_cm = None
        if placement["scale_wall_index"] is not None and placement["scale_cm"] and vertices:
            lengths = wall_lengths(vertices)
            index = placement["scale_wall_index"]
            if index < len(lengths) and lengths[index]:
                units_per_cm = lengths[index] / float(placement["scale_cm"])

        if len(vertices) >= 3:
            point = (float(placement["x"]), float(placement["y"]))
            ctx.position = position_in_room(point, vertices, units_per_cm)
            if units_per_cm:
                ctx.exposure = compute_exposure(
                    point, vertices, elements, float(placement["north_angle"]), units_per_cm
                )
                radiator = nearest_of_type(point, vertices, elements, "radiator", units_per_cm)
                ctx.radiator_m = radiator["distance_m"] if radiator else None

    ctx.exposure_alert = exposure_alert(
        ctx.exposure, plant["exposure_min"], plant["exposure_max"]
    )

    if ctx.site_id:
        # The most recent reading up to today, not strictly today's: before the
        # daily batch runs there is none, and falling back keeps climate.py in
        # play. The age travels in the payload so a stale input stays visible.
        ctx.weather = query(
            "SELECT temp_c, humidity_pct, cloud_pct, condition_id, observed_on "
            "FROM weather_log WHERE site_id = %s AND observed_on <= %s "
            "ORDER BY observed_on DESC LIMIT 1",
            (ctx.site_id, ctx.today),
            fetch="one",
        )
        if ctx.weather:
            ctx.weather_age_days = (ctx.today - ctx.weather["observed_on"]).days

    for row in query(
        "SELECT DISTINCT ON (action) action, done_at FROM care_log "
        "WHERE plant_id = %s ORDER BY action, done_at DESC",
        (plant_id,),
        fetch="all",
    ):
        ctx.last_care[row["action"]] = row["done_at"]

    ctx.health = query(
        "SELECT status, noted_on, note FROM plant_health WHERE plant_id = %s "
        "ORDER BY noted_on DESC, id DESC LIMIT 1",
        (plant_id,),
        fetch="one",
    )

    # The repotting date is the pot's own attachment, not the cachepot's
    ctx.last_potted_on = pot["attached_on"] if pot else None

    # The five factors, then the clipped product
    outdoor_temp = float(ctx.weather["temp_c"]) if ctx.weather and ctx.weather["temp_c"] else None
    outdoor_humidity = (
        float(ctx.weather["humidity_pct"]) if ctx.weather and ctx.weather["humidity_pct"] else None
    )
    ctx.temp_c, ctx.humidity_pct = outdoor_temp, outdoor_humidity

    # A plant indoors does not live in the weather station's air: the room
    # follows the outside loosely, and warming that air collapses its humidity
    if ctx.environment == "indoor" and outdoor_temp is not None:
        cloud = ctx.weather["cloud_pct"] if ctx.weather else None
        ctx.temp_c = indoor_temperature(outdoor_temp, cloud, ctx.today.month)
        if outdoor_humidity is not None:
            ctx.humidity_pct = indoor_humidity(outdoor_temp, outdoor_humidity, ctx.temp_c)

    ctx.factors = {
        "porous": factor_porous(ctx.material_is_porous, has_cachepot=ctx.cachepot_name is not None),
        "drainage": factor_drainage(ctx.drains),
        "exposure": factor_exposure(ctx.exposure),
        "temperature": factor_temperature(ctx.temp_c),
        "humidity": factor_humidity(ctx.humidity_pct),
        "radiator": factor_radiator(ctx.radiator_m, ctx.today.month),
    }
    product = 1.0
    for value in ctx.factors.values():
        product *= value
    ctx.factors["product"] = min(FACTOR_CEILING, max(FACTOR_FLOOR, product))

    if ctx.base_interval:
        ctx.interval = max(1, round(ctx.base_interval * ctx.factors["product"]))
    return ctx


# --- due dates

MONTH_NAMES = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}


@dataclass
class Verdict:
    """Why an action is due, or why it is not.

    due_on is computed whatever the month window: an overdue repotting stays
    overdue out of season, and saying so is the whole point — "out of window"
    alone hides that the plant is two years late.
    """

    action: str
    due_on: date | None = None
    last_on: date | None = None
    interval: int | None = None
    unit: str = "jours"
    window: tuple[int, int] | None = None
    in_window: bool = True
    is_due: bool = False
    # Due only through the long-overdue escape hatch: to plan, not to do now
    planning: bool = False
    # Set when something forbids the action outright, whatever the due date
    blocker: str | None = None
    late_days: int = 0
    next_window_on: date | None = None
    reason: str = ""

    def window_label(self) -> str:
        if not self.window:
            return ""
        return f"{MONTH_NAMES[self.window[0]]} → {MONTH_NAMES[self.window[1]]}"


def next_window_start(today: date, start: int, end: int) -> date:
    """First day of the next opening of a month window."""
    year = today.year if today.month < start else today.year + 1
    # A window wrapping the new year reopens this same year when we sit past its end
    if start > end and end < today.month < start:
        year = today.year
    return date(year, start, 1)


def _last_care_date(ctx: Context, action: str) -> date | None:
    done = ctx.last_care.get(action)
    return done.astimezone(ZoneInfo(ctx.timezone)).date() if done else None


def assess(ctx: Context, action: str) -> Verdict:
    """Single source of truth for due dates: generate() and preview() both use it."""
    species = ctx.species

    if action == "watering":
        verdict = Verdict(action, interval=ctx.interval, last_on=_last_care_date(ctx, "watering"))
        if not ctx.interval:
            verdict.reason = "aucun intervalle d'arrosage pour cette saison"
            return verdict
    elif action == "fertilizing":
        verdict = Verdict(
            action,
            interval=species["fertilizing_interval_days"],
            last_on=_last_care_date(ctx, "fertilizing"),
            window=(
                (species["fertilizing_month_start"], species["fertilizing_month_end"])
                if species["fertilizing_month_start"]
                else None
            ),
        )
        if not species["fertilizing_interval_days"]:
            verdict.reason = "aucun intervalle de fertilisation défini"
            return verdict
        if ctx.last_potted_on is not None:
            since = (ctx.today - ctx.last_potted_on).days
            if since < REPOTTING_FERTILIZING_GAP_DAYS:
                verdict.blocker = (
                    f"rempotée il y a {since} jour(s), substrat encore neuf "
                    f"(délai de {REPOTTING_FERTILIZING_GAP_DAYS} jours)"
                )
        # The state of the plant outranks the calendar, and the substrate delay
        status = (ctx.health or {}).get("status")
        if status in FERTILIZING_BLOCKED_BY:
            verdict.blocker = FERTILIZING_BLOCKED_BY[status]
    elif action == "repotting":
        # Read from potting, the single source of truth for containers
        verdict = Verdict(
            action,
            interval=species["repotting_interval_months"],
            unit="mois",
            last_on=ctx.last_potted_on,
            window=(
                (species["repotting_month_start"], species["repotting_month_end"])
                if species["repotting_month_start"]
                else None
            ),
        )
        if not species["repotting_interval_months"]:
            verdict.reason = "aucun intervalle de rempotage défini"
            return verdict
    else:
        return Verdict(action, reason="action hors du périmètre du moteur")

    if verdict.last_on is None:
        verdict.due_on = ctx.today
    elif action == "repotting":
        verdict.due_on = verdict.last_on + timedelta(days=30 * verdict.interval)
    else:
        verdict.due_on = verdict.last_on + timedelta(days=verdict.interval)

    if verdict.window:
        verdict.in_window = in_month_window(ctx.today.month, *verdict.window)

    elapsed = verdict.due_on <= ctx.today
    verdict.late_days = max(0, (ctx.today - verdict.due_on).days)

    if elapsed and not verdict.in_window:
        verdict.next_window_on = next_window_start(ctx.today, *verdict.window)
        # Long overdue: notified as a planning item rather than left silent
        verdict.planning = verdict.late_days >= OVERDUE_ESCALATION_DAYS

    verdict.is_due = elapsed and (verdict.in_window or verdict.planning) and not verdict.blocker

    if verdict.blocker:
        verdict.reason = verdict.blocker
    elif not elapsed:
        verdict.reason = f"dans {(verdict.due_on - ctx.today).days} jour(s)"
    elif verdict.in_window:
        verdict.reason = "échue"
    elif verdict.planning:
        verdict.reason = (
            f"échue depuis {verdict.late_days} jour(s), hors fenêtre "
            f"({verdict.window_label()}) — à planifier"
        )
    else:
        verdict.reason = (
            f"échue depuis {verdict.late_days} jour(s), hors fenêtre ({verdict.window_label()})"
        )
    return verdict


ACTIONS = ("watering", "fertilizing", "repotting")


def assess_all(ctx: Context) -> list[Verdict]:
    return [assess(ctx, action) for action in ACTIONS]


def generate(plant_id: int, batch_run_id: int | None = None) -> list[str]:
    """Opens a reminder per action that has come due. Returns the actions opened."""
    ctx = context(plant_id)
    if ctx is None:
        return []

    opened = []
    for verdict in assess_all(ctx):
        if not verdict.is_due:
            continue
        # The partial unique index allows only one open reminder per plant and action
        existing = query(
            "SELECT id FROM reminder WHERE plant_id = %s AND action = %s AND completed_at IS NULL",
            (plant_id, verdict.action),
            fetch="one",
        )
        if existing:
            continue
        query(
            "INSERT INTO reminder (plant_id, action, due_on, is_generated, batch_run_id) "
            "VALUES (%s, %s, %s, true, %s)",
            (plant_id, verdict.action, verdict.due_on, batch_run_id),
        )
        opened.append(verdict.action)
    return opened


# --- message

SEASON_LABELS = {
    "spring": "au printemps",
    "summer": "en été",
    "autumn": "en automne",
    "winter": "en hiver",
}

ACTION_LABELS = {
    "watering": ("Arrosage", "Dernier arrosage"),
    "fertilizing": ("Fertilisation", "Dernière fertilisation"),
    "repotting": ("Rempotage", "Dernier rempotage"),
}


def _rhythm(ctx: Context, verdict) -> str:
    """What to do and how often, for a plant with no history yet.

    Without this line the very first notification of every action would say
    nothing actionable — the least informative message of all, sent exactly
    when the user knows the least.
    """
    if not verdict.interval:
        return ""
    parts = [f"Rythme : tous les {verdict.interval} {verdict.unit}"]
    if verdict.action == "watering":
        parts.append(f" {SEASON_LABELS[ctx.season]}")
    if verdict.window:
        parts.append(f", fenêtre {verdict.window_label()}")
    return "".join(parts) + "."


def justification(ctx: Context) -> str:
    """Only the factors that actually moved, in plain words. Empty when all neutral."""
    reasons = []
    factors = ctx.factors

    if factors.get("porous", 1) < 1:
        reasons.append(f"pot en {(ctx.material_label or 'matière poreuse').lower()}")
    if factors.get("drainage", 1) > 1:
        contenant = "cache-pot" if ctx.cachepot_name else "pot"
        reasons.append(f"{contenant} sans drainage")
    if factors.get("exposure", 1) < 0.98:
        reasons.append("exposition lumineuse")
    elif factors.get("exposure", 1) > 1.05:
        reasons.append("peu de lumière")
    if factors.get("temperature", 1) < 1 and ctx.temp_c is not None:
        reasons.append(f"chaleur ({ctx.temp_c:.0f} °C)")
    humidity = factors.get("humidity", 1)
    if humidity != 1 and ctx.humidity_pct is not None:
        level = "humide" if humidity > 1 else "sec"
        reasons.append(f"air {level} ({ctx.humidity_pct:.0f} %)")
    if factors.get("radiator", 1) < 1 and ctx.radiator_m:
        reasons.append(f"radiateur à {ctx.radiator_m:.1f} m".replace(".", ","))

    return ", ".join(reasons).capitalize() + "." if reasons else ""


def _days_since(ctx: Context, action: str) -> int | None:
    if action == "repotting":
        reference = ctx.last_potted_on
    else:
        done = ctx.last_care.get(action)
        reference = done.astimezone(ZoneInfo(ctx.timezone)).date() if done else None
    return (ctx.today - reference).days if reference else None


def message(ctx: Context, action: str, verdict=None) -> tuple[str, str]:
    """Short and concrete: what to do, how much, why."""
    label, last_label = ACTION_LABELS.get(action, (action.capitalize(), "Dernier"))
    title = f"{label} — {ctx.plant_name}"
    verdict = verdict if verdict is not None else assess(ctx, action)

    # Out of season but long overdue: say when it can be done, not what to do now
    if verdict.planning:
        months = round(verdict.late_days / 30)
        return title, "\n".join([
            f"En retard de {verdict.late_days} jours, soit environ {months} mois.",
            f"Fenêtre possible : {verdict.window_label()}.",
            f"Prochaine occasion : {MONTH_NAMES[verdict.next_window_on.month]} "
            f"{verdict.next_window_on.year}.",
        ])

    lines = []
    if action == "watering" and ctx.volume_ml:
        lines.append(f"{ctx.volume_ml} ml.")

    # The verdict already carries the interval, its unit and the month window:
    # reading them from there keeps one source of truth for the rhythm
    days = _days_since(ctx, action)
    if days is None:
        lines.append("Première fois, aucun antécédent enregistré.")
        rhythm = _rhythm(ctx, verdict)
        if rhythm:
            lines.append(rhythm)
    elif verdict.interval:
        lines.append(f"{last_label} il y a {days} jours, intervalle de {verdict.interval} {verdict.unit}.")
    else:
        lines.append(f"{last_label} il y a {days} jours.")

    if action == "watering":
        reason = justification(ctx)
        if reason:
            lines.append(reason)
        # Spacing the waterings reduces how much goes in; it does not remove
        # what already sits at the bottom. Only emptying does.
        if ctx.factors.get("drainage", 1) > 1:
            contenant = "le cache-pot" if ctx.cachepot_name else "la soucoupe"
            lines.append(f"Vider {contenant} 20 minutes après l'arrosage.")
        # Placement, not care: it rides the watering message because that is the one
        # already carrying the "why", and it is the message that comes back often
        if ctx.exposure_alert:
            lines.append(ctx.exposure_alert)

    return title, "\n".join(lines)
