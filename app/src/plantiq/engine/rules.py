# app/src/plantiq/engine/rules.py

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from plantiq.core.database import query
from plantiq.engine.climate import indoor_humidity, indoor_temperature
from plantiq.engine.geometry import wall_lengths
from plantiq.engine.light import (
    ExposureLevel,
    attenuated_intensity,
    nearest_of_type,
    position_in_room,
)
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

# A container without a hole is not a coefficient. Spacing the waterings
# reduces how much goes in; it does nothing about what already sits at the
# bottom, and only emptying does. So no factor — an instruction instead, in the
# message. The outer shell decides: a cachepot without a hole overrides a
# pierced pot sitting inside it.
DRAINAGE_INSTRUCTION_MINUTES = 20

# Every fifth watering is a flush: at 200 ml per litre the water already runs
# out of the bottom, but only a deliberate double dose carries the accumulated
# salts out with it. An engine rule, not a species field — it follows from how
# fertiliser builds up in any substrate.
LEACHING_EVERY = 5

# An appliance blowing on a plant is a placement problem, not a care task.
# Distance under which it is worth saying so, and the months each one runs.
PLACEMENT_ALERT_M = 1.0
COOLING_MONTHS = {6, 7, 8, 9}

# Atmospheric reference for factor_humidity, not a species parameter: at equal
# humidity the air dries a Yucca's pot and a Spathiphyllum's at the same speed.
# That is evaporation physics, so the pivot is the same for every species — the
# species' own sensitivity already lives in species_watering, and moving the
# pivot per species would count the same gap twice.
REFERENCE_RH = 60.0


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _number(value) -> float | None:
    """Decimal or None into a JSON-serialisable float. Zero stays zero."""
    return float(value) if value is not None else None


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
    # Experienced humidity against the species' physiological floor
    humidity_alert: str | None = None
    # What the spot does to the plant: heat source, cold draught, raw sun
    placement_alerts: list = field(default_factory=list)
    position: str | None = None
    radiator_m: float | None = None
    air_conditioner_m: float | None = None
    weather: dict | None = None
    # What the plant actually experiences: converted indoors, raw outdoors
    temp_c: float | None = None
    humidity_pct: float | None = None
    # Cloud cover of the reading: dims the light, never the water directly
    cloud_pct: float | None = None
    # 0 when today's reading exists, higher when falling back on an older one
    weather_age_days: int | None = None

    last_care: dict = field(default_factory=dict)
    last_potted_on: date | None = None
    # Waterings already logged, for the leaching cycle
    watering_count: int = 0
    # The open fertiliser, for the dose carried in the fertilizing payload
    fertilizer: dict | None = None
    fertilizer_choices: int = 0
    # Most recent plant_health row: there is no status column on plant
    health: dict | None = None

    factors: dict = field(default_factory=dict)
    interval: int | None = None
    species: dict = field(default_factory=dict)
    material_label: str | None = None

    def payload(self, action: str = "watering") -> dict:
        """Inputs of the decision, stored with the notification.

        Split by action: a repotting reminder has no business carrying
        millilitres of watering, and a fertilizing one needs the dose rather
        than the interval. What every action shares — where the plant sits,
        what air it sits in, how it was doing — stays common.
        """
        common = {
            "action": action,
            "position": self.position,
            "environment": self.environment,
            "placement_alerts": self.placement_alerts,
            "health": (
                {
                    "status": self.health["status"],
                    "noted_on": self.health["noted_on"].isoformat(),
                }
                if self.health
                else None
            ),
            "weather": (
                {
                    "temp_c": _number(self.weather["temp_c"]),
                    "humidity_pct": _number(self.weather["humidity_pct"]),
                    "cloud_pct": self.weather["cloud_pct"],
                    "observed_on": self.weather["observed_on"].isoformat(),
                    "age_days": self.weather_age_days,
                }
                if self.weather
                else None
            ),
            # The pair the factors were actually computed from
            "effective": {
                "temp_c": round(self.temp_c, 1) if self.temp_c is not None else None,
                "humidity_pct": (
                    round(self.humidity_pct, 1) if self.humidity_pct is not None else None
                ),
                "converted": self.environment == "indoor" and self.weather is not None,
            },
        }

        if action == "fertilizing":
            return common | {
                "interval_days": self.species.get("fertilizing_interval_days"),
                "last_on": _iso(self.last_care.get("fertilizing")),
                "fertilizer": (
                    {
                        "name": self.fertilizer["name"],
                        "npk": self.fertilizer["npk"],
                        "dilution_ml_per_l": _number(self.fertilizer["dilution_ml_per_l"]),
                        "dose_ml": self._dose_ml(),
                        # Nothing links a plant to its fertiliser: more than one
                        # open bottle makes the dose above a guess
                        "open_choices": self.fertilizer_choices,
                    }
                    if self.fertilizer
                    else None
                ),
            }

        if action == "repotting":
            years = (
                (self.today - self.last_potted_on).days / 365.25 if self.last_potted_on else None
            )
            return common | {
                "interval_months": self.species.get("repotting_interval_months"),
                "last_potted_on": _iso(self.last_potted_on),
                # Two dates, two questions. due_on keeps the lateness, which is
                # true and useful; act_on says when it should actually be done,
                # and repotting a Yucca in August because a 2024 due date says
                # so is how a correct reminder produces a bad gesture.
                "act_on": _iso(self.act_on()),
                "pot_volume_l": self.volume_l,
                "years_since": round(years, 2) if years else None,
                # Indicative only. The calendar interval remains the trigger:
                # litres per year has no calibrated threshold yet, and root-bound
                # is an observation, not a ratio.
                "litres_per_year": (
                    round(self.volume_l / years, 2) if years and self.volume_l else None
                ),
            }

        return common | {
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
            "volume_ml": self.watering_ml(),
            "leaching": is_leaching_due(self.watering_count),
            "watering_count": self.watering_count,
            "humidity_alert": self.humidity_alert,
            "container": {
                "material": self.material_label,
                "porous": self.material_is_porous,
                "cachepot": self.cachepot_name,
                "drains": self.drains,
            },
            "radiator_m": round(self.radiator_m, 2) if self.radiator_m else None,
            "air_conditioner_m": (
                round(self.air_conditioner_m, 2) if self.air_conditioner_m else None
            ),
            "exposure": (
                {
                    "intensity": round(self.exposure.intensity, 3),
                    # What the factor was computed on: the geometry dimmed by
                    # the sky. The level above stays the structural one.
                    "intensity_clouded": round(
                        attenuated_intensity(self.exposure.intensity, self.cloud_pct), 3
                    ),
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
        }

    def act_on(self) -> date | None:
        """When the repotting should be carried out, as opposed to when it fell due.

        Today when the month window is open or the species declares none;
        otherwise the first day of the next opening.
        """
        start = self.species.get("repotting_month_start")
        end = self.species.get("repotting_month_end")
        if start is None or end is None or in_month_window(self.today.month, start, end):
            return self.today
        return next_window_start(self.today, start, end)

    def watering_ml(self) -> int | None:
        """The dose to pour, doubled on the flush."""
        if self.volume_ml is None:
            return None
        return self.volume_ml * 2 if is_leaching_due(self.watering_count) else self.volume_ml

    def _dose_ml(self) -> float | None:
        """Fertiliser to measure out, for the water volume of one watering."""
        dilution = _number(self.fertilizer["dilution_ml_per_l"]) if self.fertilizer else None
        litres = (self.watering_ml() or 0) / 1000
        return round(dilution * litres, 1) if dilution and litres else None


# --- factors, each neutral at 1.00


def factor_porous(is_porous: bool | None, has_cachepot: bool = False) -> float:
    # Terracotta breathes through its walls — unless it sits inside a cachepot,
    # which seals those walls off and cancels the effect entirely
    if has_cachepot:
        return 1.00
    return 0.85 if is_porous else 1.00


def factor_exposure(exposure, cloud_pct: float | None = None) -> float:
    """On the light actually received: the geometry, dimmed by today's sky.

    A March day at 10 % cloud evaporates far more than one at 100 %, and the
    sky is the only thing that says so. It lands here rather than as a factor
    of its own, because the sky modulates the light and not the water.
    """
    # Unknown exposure stays neutral: a dark room is not the same as no data
    if exposure is None:
        return 1.00
    return 1.15 - 0.25 * min(attenuated_intensity(exposure.intensity, cloud_pct), 2)


def factor_temperature(temp_c: float | None) -> float:
    if temp_c is None:
        return 1.00
    return max(0.85, 1 - 0.015 * max(0.0, temp_c - 25))


def factor_humidity(humidity_pct: float | None) -> float:
    if humidity_pct is None:
        return 1.00
    return min(1.10, max(0.90, 1 + 0.004 * (humidity_pct - REFERENCE_RH)))


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

    measured = ExposureLevel[exposure.level]
    label = EXPOSURE_LABELS[exposure.level]
    if measured < ExposureLevel[exposure_min]:
        return (
            f"Lumière insuffisante : exposition {label}, "
            f"l'espèce demande au moins {EXPOSURE_LABELS[exposure_min]}."
        )
    if measured > ExposureLevel[exposure_max]:
        return (
            f"Lumière excessive : exposition {label}, "
            f"l'espèce tolère au plus {EXPOSURE_LABELS[exposure_max]}."
        )
    return None


def humidity_alert(humidity_pct: float | None, humidity_min_pct: int | None) -> str | None:
    """Names the gap when the air sits below what the species tolerates.

    A physiological threshold, read on the humidity the plant actually
    experiences — converted indoors. It never touches the watering interval:
    dry air browns the leaf margins, which says nothing about how fast the
    substrate dries. Silent when either side is unknown.
    """
    if humidity_pct is None or humidity_min_pct is None:
        return None
    if humidity_pct >= humidity_min_pct:
        return None
    return (
        f"Air trop sec : {humidity_pct:.0f} %, "
        f"l'espèce demande au moins {humidity_min_pct} %."
    )


def placement_alerts(ctx: "Context") -> list[str]:
    """What the spot itself does to the plant, whatever the watering says.

    Each appliance only speaks in the months it runs: a radiator in July is a
    piece of furniture. A plant noted `stressed` lifts that restriction — when
    something is already going wrong, the season is a poor reason to stay
    silent about a heat source 30 cm away.

    Never touches the interval. Reported, like every other diagnostic here.
    """
    fragile = (ctx.health or {}).get("status") == "stressed"
    alerts = []

    if ctx.radiator_m is not None and ctx.radiator_m < PLACEMENT_ALERT_M:
        if fragile or ctx.today.month in HEATING_MONTHS:
            alerts.append(
                f"Radiateur à {ctx.radiator_m * 100:.0f} cm : air asséché et racines "
                f"réchauffées, éloigner la plante pendant la période de chauffe."
            )

    if ctx.air_conditioner_m is not None and ctx.air_conditioner_m < PLACEMENT_ALERT_M:
        if fragile or ctx.today.month in COOLING_MONTHS:
            alerts.append(
                f"Climatiseur à {ctx.air_conditioner_m * 100:.0f} cm : souffle froid et sec, "
                f"éloigner la plante du flux."
            )

    # Direct sun on a species that only tolerates it filtered burns the leaves
    if (
        ctx.exposure is not None
        and ctx.exposure.level == ExposureLevel.direct.name
        and ctx.species.get("sun_tolerance") == "filtered"
    ):
        alerts.append(
            "Soleil direct alors que l'espèce ne le tolère que filtré : "
            "voiler la fenêtre ou reculer la plante."
        )

    return alerts


def is_leaching_due(watering_count: int) -> bool:
    """True when the next watering is the flush.

    Counted on waterings, not on days: what accumulates is fertiliser, and it
    accumulates per dose. The count is what has already been logged, so the
    fifth watering is the one where the count reaches four.
    """
    return (watering_count + 1) % LEACHING_EVERY == 0


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
               sp.exposure_min, sp.exposure_max, sp.humidity_min_pct, sp.sun_tolerance,
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
        row["container_type"]: row
        for row in query(
            """
            SELECT pc.container_type, pc.valid_from, c.name, c.volume_l, c.has_drainage,
                   m.is_porous, m.label AS material_label
            FROM plant_container pc JOIN container c ON c.id = pc.container_id
            LEFT JOIN material m ON m.id = c.material_id
            WHERE pc.plant_id = %s AND pc.closed_at IS NULL
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
                cooler = nearest_of_type(
                    point, vertices, elements, "air_conditioner", units_per_cm
                )
                ctx.air_conditioner_m = cooler["distance_m"] if cooler else None

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

    ctx.watering_count = query(
        "SELECT count(*) AS total FROM care_log WHERE plant_id = %s AND action = 'watering'",
        (plant_id,),
        fetch="one",
    )["total"]

    ctx.health = query(
        "SELECT status, noted_on, note FROM plant_health WHERE plant_id = %s "
        "ORDER BY noted_on DESC, id DESC LIMIT 1",
        (plant_id,),
        fetch="one",
    )

    # Nothing links a plant to the fertiliser used on it, so the open one is
    # taken as the one in use. The count travels in the payload: two open
    # bottles make the dose ambiguous, and that has to be visible.
    fertilizers = query(
        "SELECT name, npk, dilution_ml_per_l FROM consumable "
        "WHERE type = 'fertilizer' AND closed_at IS NULL ORDER BY id DESC",
        fetch="all",
    )
    ctx.fertilizer = fertilizers[0] if fertilizers else None
    ctx.fertilizer_choices = len(fertilizers)

    # The repotting date is the pot's own period, not the cachepot's
    ctx.last_potted_on = pot["valid_from"] if pot else None

    # The five factors, then the clipped product
    # Tested against None, never truthiness: 0 °C is a reading, not a missing
    # value, and it is exactly the reading the indoor conversion matters for
    outdoor_temp = _number(ctx.weather["temp_c"]) if ctx.weather else None
    outdoor_humidity = _number(ctx.weather["humidity_pct"]) if ctx.weather else None
    ctx.cloud_pct = _number(ctx.weather["cloud_pct"]) if ctx.weather else None
    ctx.temp_c, ctx.humidity_pct = outdoor_temp, outdoor_humidity

    # A plant indoors does not live in the weather station's air: the room
    # follows the outside loosely, and warming that air collapses its humidity
    if ctx.environment == "indoor" and outdoor_temp is not None:
        ctx.temp_c = indoor_temperature(outdoor_temp)
        if outdoor_humidity is not None:
            ctx.humidity_pct = indoor_humidity(outdoor_temp, outdoor_humidity, ctx.temp_c)

    # On the experienced humidity, so an indoor plant is judged on the air it
    # actually sits in and not on the weather station's
    ctx.humidity_alert = humidity_alert(ctx.humidity_pct, plant["humidity_min_pct"])
    ctx.placement_alerts = placement_alerts(ctx)

    ctx.factors = {
        "porous": factor_porous(ctx.material_is_porous, has_cachepot=ctx.cachepot_name is not None),
        "exposure": factor_exposure(ctx.exposure, ctx.cloud_pct),
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
    # care_log.done_at is a date: nothing here reads an hour off a care
    return ctx.last_care.get(action)


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
        # Read from plant_container, the single source of truth for containers
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
    reference = ctx.last_potted_on if action == "repotting" else ctx.last_care.get(action)
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
    leaching = action == "watering" and is_leaching_due(ctx.watering_count)
    if action == "watering" and ctx.watering_ml():
        lines.append(f"{ctx.watering_ml()} ml.")

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
        # Every fifth watering flushes the accumulated fertiliser out
        if leaching:
            lines.append(
                f"Rinçage à l'évier : {LEACHING_EVERY}e arrosage, volume doublé, "
                f"laisser l'eau traverser et s'égoutter."
            )
        reason = justification(ctx)
        if reason:
            lines.append(reason)
        # An instruction, not a coefficient: spacing the waterings would reduce
        # how much goes in without removing what already sits at the bottom
        if ctx.drains is False:
            contenant = "le cache-pot" if ctx.cachepot_name else "la soucoupe"
            lines.append(
                f"Vider {contenant} {DRAINAGE_INSTRUCTION_MINUTES} minutes après l'arrosage."
            )
        # Placement and air, not care: they ride the watering message because
        # that is the one already carrying the "why", and the one that comes
        # back often. None of them has any effect on the interval above.
        if ctx.exposure_alert:
            lines.append(ctx.exposure_alert)
        if ctx.humidity_alert:
            lines.append(ctx.humidity_alert)
        lines.extend(ctx.placement_alerts)

    return title, "\n".join(lines)
