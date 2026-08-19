# app/src/plantiq/engine/climate.py

"""Indoor conditions derived from the outdoor reading.

A plant inside a heated house does not live in the weather station's air.
Two corrections matter, and the second is the one that bites in winter:

  - temperature: the room barely follows the outside when heating is on,
    and follows it loosely the rest of the year;
  - humidity: the *absolute* water content is roughly the same inside and
    outside, so warming that air collapses its relative humidity. Outside
    at 5 °C and 85 %, the same air at 20 °C indoors sits near 32 %.
"""

import math

# Magnus-Tetens over water, WMO coefficients
MAGNUS_A = 17.62
MAGNUS_B = 243.12
MAGNUS_C = 6.112

# Heating target, and how much the room follows the outside
SETPOINT_C = 20.5
COUPLING_HEATED = 0.15
COUPLING_FREE = 0.55

# A clear sky warms a room through its windows
SUN_BONUS_C = 1.5

INDOOR_MIN_C, INDOOR_MAX_C = 20.0, 28.0
HEATING_MONTHS = {10, 11, 12, 1, 2, 3, 4}


def saturation_pressure(temp_c: float) -> float:
    """Saturation vapour pressure in hPa."""
    return MAGNUS_C * math.exp(MAGNUS_A * temp_c / (MAGNUS_B + temp_c))


def dew_point(temp_c: float, humidity_pct: float) -> float:
    """Dew point in °C — the quantity that stays put when air moves indoors."""
    ratio = math.log(max(humidity_pct, 0.1) / 100) + MAGNUS_A * temp_c / (MAGNUS_B + temp_c)
    return MAGNUS_B * ratio / (MAGNUS_A - ratio)


def indoor_temperature(
    outdoor_c: float, cloud_pct: float | None, month: int
) -> float:
    """Room temperature, blended between the heating setpoint and the outside."""
    heated = month in HEATING_MONTHS
    coupling = COUPLING_HEATED if heated else COUPLING_FREE
    temperature = SETPOINT_C + coupling * (outdoor_c - SETPOINT_C)

    # Solar gain only counts when the heating is not already holding the room
    if not heated and cloud_pct is not None:
        temperature += SUN_BONUS_C * (1 - cloud_pct / 100)

    return min(INDOOR_MAX_C, max(INDOOR_MIN_C, temperature))


def indoor_humidity(outdoor_c: float, outdoor_humidity_pct: float, indoor_c: float) -> float:
    """Same air, warmer: relative humidity falls as saturation pressure rises."""
    vapour = outdoor_humidity_pct / 100 * saturation_pressure(outdoor_c)
    relative = 100 * vapour / saturation_pressure(indoor_c)
    return min(100.0, max(1.0, relative))
