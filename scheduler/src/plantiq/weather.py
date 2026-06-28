# scheduler/src/plantiq/weather.py

import httpx

from plantiq.core.config import OPENWEATHERMAP_API_KEY
from plantiq.core.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

_OWM_CONDITION = {
    "Clear":        "sunny",
    "Clouds":       "cloudy",
    "Rain":         "rainy",
    "Drizzle":      "rainy",
    "Thunderstorm": "stormy",
    "Snow":         "snowy",
}


def get_weather(lat: float, lon: float) -> dict:
    """Fetch current weather by coordinates. Returns normalized dict."""
    response = httpx.get(
        _BASE_URL,
        params={"lat": lat, "lon": lon, "appid": OPENWEATHERMAP_API_KEY, "units": "metric"},
        timeout=10,
    )
    response.raise_for_status()
    raw = response.json()
    owm_main = (raw.get("weather") or [{}])[0].get("main", "")
    return {
        "temperature_min": raw["main"].get("temp_min"),
        "temperature_max": raw["main"].get("temp_max"),
        "humidity":        raw["main"].get("humidity"),
        "condition":       _OWM_CONDITION.get(owm_main, "cloudy"),
        "wind_speed":      (raw.get("wind") or {}).get("speed"),
    }
