# app/src/plantiq/engine/climate.py

"""Indoor conditions derived from the outdoor reading.

A plant inside a heated house does not live in the weather station's air.
Two corrections matter, and the second is the one that bites in winter:

  - temperature: the room sits near its setpoint and follows the outside
    asymmetrically — heat gets in, cold is held off by the heating;
  - humidity: the *absolute* water content is roughly the same inside and
    outside, so warming that air collapses its relative humidity. Outside
    at 5 °C and 90 %, the same air at 19,4 °C indoors reads near 35 %.
"""

import math

# Magnus-Tetens over water, WMO coefficients
MAGNUS_A = 17.62
MAGNUS_B = 243.12
MAGNUS_C = 6.112

# The room is held near this, and follows the outside asymmetrically: a hot day
# pushes it up noticeably, a cold one barely moves it because the heating
# absorbs the swing. The asymmetry replaces a calendar of heating months — what
# decides is whether it is warmer outside than the setpoint, not the date.
INDOOR_SETPOINT_C = 21.0
COUPLING_ABOVE = 0.4
COUPLING_BELOW = 0.1


def saturation_pressure(temp_c: float) -> float:
    """Saturation vapour pressure in hPa."""
    return MAGNUS_C * math.exp(MAGNUS_A * temp_c / (MAGNUS_B + temp_c))


def dew_point(temp_c: float, humidity_pct: float) -> float:
    """Dew point in °C — the quantity that stays put when air moves indoors."""
    ratio = math.log(max(humidity_pct, 0.1) / 100) + MAGNUS_A * temp_c / (MAGNUS_B + temp_c)
    return MAGNUS_B * ratio / (MAGNUS_A - ratio)


def indoor_temperature(outdoor_c: float) -> float:
    """Room temperature, damped towards the setpoint.

    No clamp: the previous floor of 20 °C made a cold room unrepresentable,
    which in turn made any cold alert structurally silent. 10 °C outside now
    reads 19,9 °C indoors rather than exactly 20.
    """
    coupling = COUPLING_ABOVE if outdoor_c > INDOOR_SETPOINT_C else COUPLING_BELOW
    return INDOOR_SETPOINT_C + coupling * (outdoor_c - INDOOR_SETPOINT_C)


def indoor_humidity(outdoor_c: float, outdoor_humidity_pct: float, indoor_c: float) -> float:
    """Same air, warmer: relative humidity falls as saturation pressure rises."""
    vapour = outdoor_humidity_pct / 100 * saturation_pressure(outdoor_c)
    relative = 100 * vapour / saturation_pressure(indoor_c)
    return min(100.0, max(1.0, relative))
