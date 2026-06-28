# scheduler/tests/test_engine_rules.py

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from plantiq.engine import (
    TZ,
    _rule_fertilizing,
    _rule_health_check,
    _rule_misting,
    _rule_repotting,
    _rule_watering,
    _rule_weather_warning,
)

TODAY = date(2026, 6, 27)  # summer (juin)
TODAY_WINTER = date(2026, 1, 15)  # hors SUMMER_MONTHS

PLANT = {"id": "p1", "name": "Monstera", "city": "Bruxelles", "location_id": "loc1"}


# ── Builders ──────────────────────────────────────────────────────────────────

def _conn():
    return MagicMock()


def _profile(**kw):
    return {
        "watering_frequency_days_summer": 7,
        "watering_frequency_days_winter": 14,
        "watering_amount": "moderate",
        "watering_mode": "soil_only",
        "watering_quantity_ml": 300,
        "watering_instructions": "",
        "humidity_level": "low",
        "temp_min_c": None,
        "temp_max_c": None,
        "fertilizing_frequency_days": 14,
        "repotting_frequency_months": 12,
        **kw,
    }


def _container(**kw):
    return {
        "pot_type": "plastic",
        "pot_diameter_cm": 20,
        "pot_height_cm": 20,
        "has_drainage": True,
        "soil_condition": "correct",
        "soil_issues": None,
        "last_repotted": date(2026, 1, 1),  # ~6 mois — sous le seuil repotting (12m), hors cooldown fertil (60j)
        "repotting_urgent": False,
        "repotting_notes": None,
        **kw,
    }


def _weather(**kw):
    return {
        "temperature_min": 15.0,
        "temperature_max": 22.0,
        "humidity": 60,
        "condition": "cloudy",
        "wind_speed": 5.0,
        **kw,
    }


def _pl(**kw):
    return {"indoor": True, "shade": False, "near_ac": False, "near_heating": False, **kw}


def _care_log(days_ago: int) -> dict:
    return {"done_at": TODAY - timedelta(days=days_ago)}


def _notified(days_ago: int) -> dict:
    return {"sent_at": datetime.now(TZ) - timedelta(days=days_ago)}


# ── _rule_watering ────────────────────────────────────────────────────────────

def test_watering_fires_when_overdue():
    with patch("plantiq.engine.send") as mock_send:
        _rule_watering(
            _conn(), PLANT, _profile(), _pl(), _container(), [], None, _weather(),
            {"watering": _care_log(10)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_watering_autologs_care_when_fires():
    """Quand la règle déclenche, conn.execute est appelé 2 fois : _log_notification + auto-log."""
    c = _conn()
    with patch("plantiq.engine.send"):
        _rule_watering(
            c, PLANT, _profile(), _pl(), _container(), [], None, _weather(),
            {"watering": _care_log(10)}, {}, set(), TODAY, TZ,
        )
    assert c.execute.call_count == 2


def test_watering_skips_when_too_recent():
    with patch("plantiq.engine.send") as mock_send:
        _rule_watering(
            _conn(), PLANT, _profile(), _pl(), _container(), [], None, _weather(),
            {"watering": _care_log(3)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_watering_skips_when_waterlogged():
    with patch("plantiq.engine.send") as mock_send:
        _rule_watering(
            _conn(), PLANT, _profile(), _pl(), _container(soil_condition="waterlogged"),
            [], None, _weather(), {"watering": _care_log(10)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_watering_skips_when_dying():
    with patch("plantiq.engine.send") as mock_send:
        _rule_watering(
            _conn(), PLANT, _profile(), _pl(), _container(), [],
            {"status": "dying", "issue_type": "none"}, _weather(),
            {"watering": _care_log(10)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_watering_skips_when_burned():
    with patch("plantiq.engine.send") as mock_send:
        _rule_watering(
            _conn(), PLANT, _profile(), _pl(), _container(), [],
            {"status": "burned", "issue_type": "sunburn"}, _weather(),
            {"watering": _care_log(10)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_watering_skips_when_snoozed():
    with patch("plantiq.engine.send") as mock_send:
        _rule_watering(
            _conn(), PLANT, _profile(), _pl(), _container(), [], None, _weather(),
            {"watering": _care_log(10)}, {}, {"watering"}, TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_watering_skips_when_recently_notified():
    with patch("plantiq.engine.send") as mock_send:
        _rule_watering(
            _conn(), PLANT, _profile(), _pl(), _container(), [], None, _weather(),
            {"watering": _care_log(10)}, {"watering": _notified(1)}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_watering_dormant_doubles_frequency():
    """freq_base=7, dormant ×2=14 — 10 jours ne suffit pas."""
    with patch("plantiq.engine.send") as mock_send:
        _rule_watering(
            _conn(), PLANT, _profile(), _pl(), _container(), [],
            {"status": "dormant", "issue_type": "none", "treating ": None}, _weather(),
            {"watering": _care_log(10)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


# ── _rule_misting ─────────────────────────────────────────────────────────────

def test_misting_fires_when_near_ac_and_high_humidity_level():
    with patch("plantiq.engine.send") as mock_send:
        _rule_misting(
            _conn(), PLANT, _profile(humidity_level="high"), _pl(near_ac=True),
            _container(), None, _weather(humidity=60),
            {"misting": _care_log(5)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_misting_fires_when_low_ambient_humidity():
    with patch("plantiq.engine.send") as mock_send:
        _rule_misting(
            _conn(), PLANT, _profile(humidity_level="high"), _pl(),
            _container(), None, _weather(humidity=40),
            {"misting": _care_log(5)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_misting_skips_when_humidity_level_not_high():
    with patch("plantiq.engine.send") as mock_send:
        _rule_misting(
            _conn(), PLANT, _profile(humidity_level="low"), _pl(near_ac=True),
            _container(), None, _weather(humidity=40),
            {"misting": _care_log(5)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_misting_skips_when_weather_none():
    """Sans météo, humidity prend 100 par défaut — la règle ne doit pas déclencher."""
    with patch("plantiq.engine.send") as mock_send:
        _rule_misting(
            _conn(), PLANT, _profile(humidity_level="high"), _pl(),
            _container(), None, None,  # weather=None
            {"misting": _care_log(5)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_misting_skips_when_mold():
    with patch("plantiq.engine.send") as mock_send:
        _rule_misting(
            _conn(), PLANT, _profile(humidity_level="high"), _pl(near_ac=True),
            _container(soil_condition="moldy"), None, _weather(humidity=40),
            {"misting": _care_log(5)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_misting_skips_when_misted_too_recently():
    with patch("plantiq.engine.send") as mock_send:
        _rule_misting(
            _conn(), PLANT, _profile(humidity_level="high"), _pl(near_ac=True),
            _container(), None, _weather(humidity=40),
            {"misting": _care_log(2)}, {}, set(), TODAY, TZ,  # jours <= 3
        )
    mock_send.assert_not_called()


def test_misting_skips_when_snoozed():
    with patch("plantiq.engine.send") as mock_send:
        _rule_misting(
            _conn(), PLANT, _profile(humidity_level="high"), _pl(near_ac=True),
            _container(), None, _weather(humidity=40),
            {"misting": _care_log(5)}, {}, {"misting"}, TODAY, TZ,
        )
    mock_send.assert_not_called()


# ── _rule_weather_warning ─────────────────────────────────────────────────────

def test_weather_warning_fires_when_temp_exceeds_profile_max():
    with patch("plantiq.engine.send") as mock_send:
        _rule_weather_warning(
            _conn(), PLANT, _profile(temp_max_c=25.0), _pl(),
            _weather(temperature_max=30.0), None, {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_weather_warning_fires_when_temp_below_profile_min():
    with patch("plantiq.engine.send") as mock_send:
        _rule_weather_warning(
            _conn(), PLANT, _profile(temp_min_c=15.0), _pl(),
            _weather(temperature_min=10.0), None, {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_weather_warning_fires_when_indoor_heat_without_ac():
    with patch("plantiq.engine.send") as mock_send:
        _rule_weather_warning(
            _conn(), PLANT, _profile(), _pl(indoor=True, near_ac=False),
            _weather(temperature_max=36.0), None, {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_weather_warning_skips_indoor_heat_when_ac_present():
    with patch("plantiq.engine.send") as mock_send:
        _rule_weather_warning(
            _conn(), PLANT, _profile(), _pl(indoor=True, near_ac=True),
            _weather(temperature_max=36.0), None, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_weather_warning_skips_when_dying():
    with patch("plantiq.engine.send") as mock_send:
        _rule_weather_warning(
            _conn(), PLANT, _profile(temp_max_c=25.0), _pl(),
            _weather(temperature_max=30.0),
            {"status": "dying", "issue_type": "none"}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_weather_warning_skips_when_snoozed():
    with patch("plantiq.engine.send") as mock_send:
        _rule_weather_warning(
            _conn(), PLANT, _profile(temp_max_c=25.0), _pl(),
            _weather(temperature_max=30.0), None, {}, {"warning"}, TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_weather_warning_skips_when_no_conditions_met():
    with patch("plantiq.engine.send") as mock_send:
        _rule_weather_warning(
            _conn(), PLANT, _profile(), _pl(),
            _weather(), None, {}, set(), TODAY, TZ,  # météo bénigne, pas de seuils profil
        )
    mock_send.assert_not_called()


# ── _rule_health_check ────────────────────────────────────────────────────────

def test_health_check_fires_when_sick():
    with patch("plantiq.engine.send") as mock_send:
        _rule_health_check(
            _conn(), PLANT,
            {"status": "sick", "issue_type": "pest", "treating ": None},
            {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_health_check_fires_when_dying():
    with patch("plantiq.engine.send") as mock_send:
        _rule_health_check(
            _conn(), PLANT,
            {"status": "dying", "issue_type": "rootbound", "treating ": None},
            {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_health_check_skips_when_healthy():
    with patch("plantiq.engine.send") as mock_send:
        _rule_health_check(
            _conn(), PLANT,
            {"status": "healthy", "issue_type": "none"},
            {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_health_check_skips_when_none():
    with patch("plantiq.engine.send") as mock_send:
        _rule_health_check(_conn(), PLANT, None, {}, set(), TODAY, TZ)
    mock_send.assert_not_called()


def test_health_check_skips_when_recently_notified():
    """Dédup sick = 7 jours — notifié il y a 3 jours → skip."""
    with patch("plantiq.engine.send") as mock_send:
        _rule_health_check(
            _conn(), PLANT,
            {"status": "sick", "issue_type": "pest", "treating ": None},
            {"health_check": _notified(3)}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_health_check_skips_when_snoozed():
    with patch("plantiq.engine.send") as mock_send:
        _rule_health_check(
            _conn(), PLANT,
            {"status": "sick", "issue_type": "pest", "treating ": None},
            {}, {"health_check"}, TODAY, TZ,
        )
    mock_send.assert_not_called()


# ── _rule_repotting ───────────────────────────────────────────────────────────

def test_repotting_fires_when_urgent():
    with patch("plantiq.engine.send") as mock_send:
        _rule_repotting(
            _conn(), PLANT, _profile(), _container(repotting_urgent=True),
            None, {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_repotting_fires_when_overdue_by_calendar():
    """freq=12 mois, rempotage il y a ~14 mois → déclenche."""
    old = TODAY - timedelta(days=420)
    with patch("plantiq.engine.send") as mock_send:
        _rule_repotting(
            _conn(), PLANT, _profile(), _container(last_repotted=old),
            None, {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_repotting_fires_when_last_repotted_unknown():
    with patch("plantiq.engine.send") as mock_send:
        _rule_repotting(
            _conn(), PLANT, _profile(), _container(last_repotted=None),
            None, {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_repotting_fires_when_soil_exhausted():
    with patch("plantiq.engine.send") as mock_send:
        _rule_repotting(
            _conn(), PLANT, _profile(), _container(soil_condition="exhausted"),
            None, {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_repotting_skips_when_not_triggered():
    """Rempotage il y a ~6 mois (< 12), sol correct, pas urgent → skip."""
    with patch("plantiq.engine.send") as mock_send:
        _rule_repotting(
            _conn(), PLANT, _profile(), _container(),
            None, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_repotting_skips_when_snoozed():
    with patch("plantiq.engine.send") as mock_send:
        _rule_repotting(
            _conn(), PLANT, _profile(), _container(repotting_urgent=True),
            None, {}, {"repotting"}, TODAY, TZ,
        )
    mock_send.assert_not_called()


# ── _rule_fertilizing ─────────────────────────────────────────────────────────

def test_fertilizing_fires_in_summer_when_overdue():
    with patch("plantiq.engine.send") as mock_send:
        _rule_fertilizing(
            _conn(), PLANT, _profile(), _container(), None,
            {"fertilizing": _care_log(20)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_called_once()


def test_fertilizing_skips_in_winter():
    with patch("plantiq.engine.send") as mock_send:
        _rule_fertilizing(
            _conn(), PLANT, _profile(), _container(), None,
            {"fertilizing": _care_log(20)}, {}, set(), TODAY_WINTER, TZ,
        )
    mock_send.assert_not_called()


def test_fertilizing_skips_when_soil_exhausted():
    with patch("plantiq.engine.send") as mock_send:
        _rule_fertilizing(
            _conn(), PLANT, _profile(), _container(soil_condition="exhausted"), None,
            {"fertilizing": _care_log(20)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_fertilizing_skips_when_sick():
    with patch("plantiq.engine.send") as mock_send:
        _rule_fertilizing(
            _conn(), PLANT, _profile(), _container(),
            {"status": "sick", "issue_type": "pest", "treating ": None},
            {"fertilizing": _care_log(20)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_fertilizing_skips_when_repotted_recently():
    """Rempotage il y a 30 jours < 60 → cooldown actif."""
    with patch("plantiq.engine.send") as mock_send:
        _rule_fertilizing(
            _conn(), PLANT, _profile(), _container(last_repotted=TODAY - timedelta(days=30)),
            None, {"fertilizing": _care_log(20)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_fertilizing_skips_when_no_frequency_defined():
    with patch("plantiq.engine.send") as mock_send:
        _rule_fertilizing(
            _conn(), PLANT, _profile(fertilizing_frequency_days=None), _container(), None,
            {"fertilizing": _care_log(20)}, {}, set(), TODAY, TZ,
        )
    mock_send.assert_not_called()


def test_fertilizing_skips_when_not_overdue():
    with patch("plantiq.engine.send") as mock_send:
        _rule_fertilizing(
            _conn(), PLANT, _profile(), _container(), None,
            {"fertilizing": _care_log(5)}, {}, set(), TODAY, TZ,  # 5 < 14 jours
        )
    mock_send.assert_not_called()


def test_fertilizing_skips_when_snoozed():
    with patch("plantiq.engine.send") as mock_send:
        _rule_fertilizing(
            _conn(), PLANT, _profile(), _container(), None,
            {"fertilizing": _care_log(20)}, {}, {"fertilizing"}, TODAY, TZ,
        )
    mock_send.assert_not_called()
