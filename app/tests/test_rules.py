# app/tests/test_rules.py

from datetime import date, timedelta

import pytest

from plantiq.engine.climate import dew_point, indoor_humidity, indoor_temperature
from plantiq.engine.light import Exposure
from plantiq.engine.rules import (
    REPOTTING_FERTILIZING_GAP_DAYS,
    Context,
    assess,
    blended_interval,
    exposure_alert,
    factor_exposure,
    factor_porous,
    humidity_alert,
    in_month_window,
    is_leaching_due,
    message,
    next_window_start,
    placement_alerts,
    season_blend,
)

TODAY = date(2026, 8, 18)
ZONE = "Europe/Brussels"

SPECIES = {
    "fertilizing_interval_days": 30,
    "fertilizing_month_start": 4,
    "fertilizing_month_end": 9,
    "repotting_interval_months": 36,
    "repotting_month_start": 3,
    "repotting_month_end": 4,
}


def make_context(**overrides) -> Context:
    """A context built by hand: assess() reads fields only, never the database."""
    ctx = Context(plant_id=1, plant_name="Test", species_name="Testus")
    ctx.today = TODAY
    ctx.timezone = ZONE
    ctx.interval = 10
    ctx.species = dict(SPECIES)
    for name, value in overrides.items():
        setattr(ctx, name, value)
    return ctx


def care_on(day: date) -> date:
    # care_log.done_at is a date: no hour is ever read off a care
    return day


# --- fertilizing blocked by a recent repotting


def test_recent_repotting_blocks_fertilizing():
    ctx = make_context(last_potted_on=TODAY - timedelta(days=51))
    verdict = assess(ctx, "fertilizing")
    assert not verdict.is_due
    assert "51 jour" in verdict.blocker


def test_the_blocker_lifts_on_the_sixtieth_day():
    ctx = make_context(last_potted_on=TODAY - timedelta(days=REPOTTING_FERTILIZING_GAP_DAYS))
    verdict = assess(ctx, "fertilizing")
    assert verdict.blocker is None
    assert verdict.is_due


def test_an_unknown_potting_date_blocks_nothing():
    ctx = make_context(last_potted_on=None)
    verdict = assess(ctx, "fertilizing")
    assert verdict.blocker is None
    assert verdict.is_due


def test_the_blocker_wins_over_the_overdue_escape_hatch():
    # Out of window, two years late, but repotted last month
    ctx = make_context(
        today=date(2026, 1, 15),
        last_potted_on=date(2025, 12, 20),
        last_care={"fertilizing": care_on(date(2023, 1, 1))},
    )
    verdict = assess(ctx, "fertilizing")
    assert not verdict.is_due


# --- long-overdue escape hatch


def test_an_old_out_of_window_action_is_notified_as_planning():
    ctx = make_context(last_potted_on=date(2021, 6, 26))
    verdict = assess(ctx, "repotting")
    assert verdict.planning
    assert verdict.is_due
    assert verdict.next_window_on == date(2027, 3, 1)


def test_a_recent_out_of_window_action_stays_silent():
    ctx = make_context(last_potted_on=TODAY - timedelta(days=30 * 36 + 100))
    verdict = assess(ctx, "repotting")
    assert not verdict.planning
    assert not verdict.is_due


# --- month windows


@pytest.mark.parametrize(
    ("month", "start", "end", "inside"),
    [(4, 4, 9, True), (1, 4, 9, False), (1, 10, 3, True), (6, 10, 3, False)],
)
def test_month_window_wraps_around_the_new_year(month, start, end, inside):
    assert in_month_window(month, start, end) is inside


def test_next_opening_of_a_wrapping_window():
    assert next_window_start(date(2026, 6, 10), 10, 3) == date(2026, 10, 1)
    assert next_window_start(date(2026, 8, 18), 3, 4) == date(2027, 3, 1)


# --- messages


def test_first_message_carries_the_rhythm_and_the_window():
    ctx = make_context(last_potted_on=None)
    _, body = message(ctx, "fertilizing")
    assert "Première fois" in body
    assert "tous les 30 jours" in body
    assert "avril → septembre" in body


def test_first_watering_message_carries_volume_and_season():
    ctx = make_context(last_potted_on=None, volume_ml=741, season="summer")
    _, body = message(ctx, "watering")
    assert "741 ml." in body
    assert "tous les 10 jours en été" in body


def test_message_with_history_keeps_its_short_form():
    ctx = make_context(
        last_potted_on=None,
        last_care={"fertilizing": care_on(TODAY - timedelta(days=21))},
    )
    _, body = message(ctx, "fertilizing")
    assert "il y a 21 jours" in body
    assert "Première fois" not in body


def test_planning_message_says_when_rather_than_what():
    ctx = make_context(last_potted_on=date(2021, 6, 26))
    _, body = message(ctx, "repotting")
    assert "En retard de" in body
    assert "Prochaine occasion : mars 2027" in body


# --- indoor conditions


def test_heating_collapses_the_relative_humidity():
    # Winter air at 5 °C and 90 % holds little water; indoors it reads dry
    indoor_c = indoor_temperature(5.0)
    assert indoor_c == pytest.approx(19.4)
    assert indoor_humidity(5.0, 90.0, indoor_c) == pytest.approx(34.9, abs=0.5)


@pytest.mark.parametrize(
    ("outdoor_c", "indoor_c"),
    [(35.0, 26.6), (10.0, 19.9), (20.7, 20.97), (21.0, 21.0)],
)
def test_the_room_follows_the_outside_asymmetrically(outdoor_c, indoor_c):
    # Heat gets in at 0.4, cold is held off at 0.1 — the heating absorbs the swing
    assert indoor_temperature(outdoor_c) == pytest.approx(indoor_c, abs=0.01)


def test_a_cold_snap_is_no_longer_flattened_by_a_floor():
    # The old floor of 20 °C made a cold room unrepresentable, and any cold
    # alert structurally silent with it
    assert indoor_temperature(-5.0) == pytest.approx(18.4)


def test_the_dew_point_survives_the_conversion():
    # The physical invariant: moving air indoors changes its temperature, not its water
    outdoor_c, outdoor_rh = 12.0, 88.0
    indoor_c = indoor_temperature(outdoor_c)
    indoor_rh = indoor_humidity(outdoor_c, outdoor_rh, indoor_c)
    assert dew_point(indoor_c, indoor_rh) == pytest.approx(dew_point(outdoor_c, outdoor_rh), abs=0.1)


def test_the_humidity_factor_is_capped_at_its_ceiling():
    from plantiq.engine.rules import factor_humidity

    # 1 + 0.004 x (86 - 60) = 1.104, above the 1.10 ceiling
    assert factor_humidity(86.0) == pytest.approx(1.10)
    assert factor_humidity(82.3) == pytest.approx(1.089, abs=0.001)
    assert factor_humidity(25.7) == pytest.approx(0.90)


# --- the porosity factor shortens, it never lengthens


def test_terracotta_shortens_the_interval():
    # The sign, pinned on the function rather than on a plant: plant 3 wears a
    # cachepot, which cancels porosity by design, so it would read 1.00 and
    # prove nothing about the sign
    assert factor_porous(is_porous=True) < 1
    assert factor_porous(is_porous=True) == pytest.approx(0.85)
    assert factor_porous(is_porous=False) == 1.00
    assert factor_porous(is_porous=None) == 1.00


def test_a_cachepot_seals_the_porous_walls():
    assert factor_porous(is_porous=True, has_cachepot=True) == 1.00


# --- the sky dims the light, and only the light


def test_an_overcast_sky_lengthens_the_interval():
    clear = factor_exposure(seen("bright_indirect"), cloud_pct=0)
    overcast = factor_exposure(seen("bright_indirect"), cloud_pct=100)
    # Less light received means less evaporation, so a longer interval
    assert overcast > clear
    assert factor_exposure(seen("bright_indirect"), cloud_pct=None) == clear


def test_the_sky_never_moves_the_placement_verdict():
    # The species range judges the spot, not today's weather: an overcast day
    # must not turn a well-placed plant into an under-lit one
    exposure = seen("indirect")
    assert exposure_alert(exposure, "indirect", "direct") is None
    assert exposure.level == "indirect"


def test_an_overdue_repotting_is_carried_out_in_the_window():
    # due_on keeps the lateness, act_on says when to actually do it
    ctx = make_context(last_potted_on=date(2021, 6, 26))
    assert assess(ctx, "repotting").due_on == date(2024, 6, 10)
    assert ctx.act_on() == date(2027, 3, 1)


def test_inside_the_window_the_action_date_is_today():
    ctx = make_context(today=date(2026, 3, 15), last_potted_on=date(2021, 6, 26))
    assert ctx.act_on() == date(2026, 3, 15)


# --- leaching, every fifth watering


@pytest.mark.parametrize(
    ("logged", "due"),
    [(0, False), (3, False), (4, True), (5, False), (9, True)],
)
def test_every_fifth_watering_is_a_flush(logged, due):
    assert is_leaching_due(logged) is due


def test_the_flush_doubles_the_dose_and_says_so():
    ctx = make_context(last_potted_on=None, volume_ml=726, watering_count=4)
    _, body = message(ctx, "watering")
    assert "1452 ml." in body
    assert "Rinçage à l'évier" in body


def test_an_ordinary_watering_keeps_its_dose():
    ctx = make_context(last_potted_on=None, volume_ml=726, watering_count=3)
    _, body = message(ctx, "watering")
    assert "726 ml." in body
    assert "Rinçage" not in body


# --- placement: what the spot does, whatever the interval says


def test_a_radiator_is_furniture_out_of_the_heating_season():
    ctx = make_context(radiator_m=0.27, today=date(2026, 8, 20))
    assert placement_alerts(ctx) == []


def test_a_radiator_within_a_metre_alerts_during_the_heating_season():
    ctx = make_context(radiator_m=0.27, today=date(2026, 10, 1))
    assert "Radiateur à 27 cm" in placement_alerts(ctx)[0]


def test_an_air_conditioner_alerts_in_summer():
    ctx = make_context(air_conditioner_m=0.62, today=date(2026, 8, 20))
    assert "Climatiseur à 62 cm" in placement_alerts(ctx)[0]


def test_a_stressed_plant_lifts_the_month_windows():
    # Something is already going wrong: the season is a poor reason to stay
    # silent about a heat source 27 cm away
    ctx = make_context(
        radiator_m=0.27, today=date(2026, 8, 20), health={"status": "stressed"}
    )
    assert "Radiateur" in placement_alerts(ctx)[0]


def test_direct_sun_on_a_filtered_species_alerts():
    ctx = make_context(exposure=seen("direct"))
    ctx.species["sun_tolerance"] = "filtered"
    assert "Soleil direct" in placement_alerts(ctx)[0]
    ctx.species["sun_tolerance"] = "full"
    assert placement_alerts(ctx) == []


# --- seasonal smoothing

YUCCA_SEASONS = {"spring": 12, "summer": 10, "autumn": 18, "winter": 28}


def test_far_from_a_boundary_a_single_season_carries_everything():
    assert season_blend(date(2026, 7, 15)) == [("summer", 1.0)]
    assert blended_interval(date(2026, 7, 15), YUCCA_SEASONS) == 10


def test_the_boundary_itself_splits_the_weight_evenly():
    assert dict(season_blend(date(2026, 9, 1))) == {"summer": 0.5, "autumn": 0.5}
    assert blended_interval(date(2026, 9, 1), YUCCA_SEASONS) == 14.0


@pytest.mark.parametrize(
    ("day", "interval"),
    [
        (date(2026, 8, 17), 10.0),   # window not yet open
        (date(2026, 8, 25), 12.13),  # a quarter of the way in
        (date(2026, 9, 8), 15.87),   # three quarters
        (date(2026, 9, 16), 18.0),   # window closed, autumn alone
    ],
)
def test_the_interval_slides_instead_of_jumping(day, interval):
    assert blended_interval(day, YUCCA_SEASONS) == pytest.approx(interval, abs=0.01)


def test_the_transition_is_monotonic_across_the_whole_window():
    days = [date(2026, 8, 17) + timedelta(days=n) for n in range(31)]
    values = [blended_interval(day, YUCCA_SEASONS) for day in days]
    assert values == sorted(values)
    assert values[0] == 10.0
    assert values[-1] == 18.0


def test_the_december_boundary_blends_across_the_new_year():
    assert dict(season_blend(date(2026, 12, 1))) == {"autumn": 0.5, "winter": 0.5}
    assert dict(season_blend(date(2026, 11, 20))) == pytest.approx(
        {"autumn": 0.867, "winter": 0.133}, abs=0.001
    )


def test_a_missing_season_degrades_instead_of_raising():
    assert blended_interval(date(2026, 9, 1), {"summer": 10}) == 10
    assert blended_interval(date(2026, 9, 1), {}) is None


# --- measured light against the species range


def seen(level: str) -> Exposure:
    return Exposure(intensity=0.4, level=level, distance_m=2.0, visible=True)


def test_too_little_light_names_the_gap():
    alert = exposure_alert(seen("low"), "indirect", "direct")
    assert "insuffisante" in alert
    assert "faible" in alert and "indirecte" in alert


def test_too_much_light_names_the_gap():
    alert = exposure_alert(seen("direct"), "low", "bright_indirect")
    assert "excessive" in alert
    assert "directe" in alert and "vive indirecte" in alert


@pytest.mark.parametrize("level", ["indirect", "bright_indirect", "direct"])
def test_anything_inside_the_range_stays_silent(level):
    assert exposure_alert(seen(level), "indirect", "direct") is None


def test_sitting_exactly_on_a_bound_is_not_a_violation():
    # Both plants in production sit on their own minimum: it must not alert
    assert exposure_alert(seen("low"), "low", "bright_indirect") is None
    assert exposure_alert(seen("direct"), "indirect", "direct") is None


def test_an_unmeasurable_exposure_says_nothing():
    # No calibration at all, and a window hidden behind a wall
    assert exposure_alert(None, "indirect", "direct") is None
    assert exposure_alert(Exposure(intensity=0.0, level="low"), "indirect", "direct") is None


def test_a_species_without_a_declared_range_says_nothing():
    assert exposure_alert(seen("low"), None, None) is None


# --- health blocks feeding, never watering


@pytest.mark.parametrize("status", ["dormant", "dying"])
def test_a_resting_or_failing_plant_is_not_fertilized(status):
    ctx = make_context(last_potted_on=None, health={"status": status})
    assert not assess(ctx, "fertilizing").is_due
    # Watering keeps its own verdict: a plant in trouble still drinks
    assert assess(ctx, "watering").blocker is None


def test_a_stressed_plant_is_still_fertilized():
    ctx = make_context(last_potted_on=None, health={"status": "stressed"})
    assert assess(ctx, "fertilizing").is_due


# --- experienced humidity against the species floor


def test_dry_air_names_the_species_floor():
    alert = humidity_alert(32.4, 50)
    assert "32 %" in alert
    assert "au moins 50 %" in alert


def test_humidity_sitting_on_the_floor_is_not_a_violation():
    assert humidity_alert(50.0, 50) is None


def test_an_unknown_side_of_the_humidity_check_says_nothing():
    assert humidity_alert(None, 50) is None
    assert humidity_alert(32.4, None) is None


def test_the_humidity_alert_rides_the_watering_message():
    alert = "Air trop sec : 32 %, l'espèce demande au moins 50 %."
    ctx = make_context(last_potted_on=None, volume_ml=495, humidity_alert=alert)
    assert alert in message(ctx, "watering")[1]
    # Fertilizing carries no alert: watering is the message that comes back often
    assert alert not in message(ctx, "fertilizing")[1]
