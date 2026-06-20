# scheduler/src/plantiq/weather.py

import httpx

from plantiq.core.config import OPENWEATHERMAP_API_KEY
from plantiq.core.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"


def get_weather(lat: float, lon: float) -> dict:
    """Fetch current weather by coordinates. Returns raw OWM response."""
    response = httpx.get(
        _BASE_URL,
        params={"lat": lat, "lon": lon, "appid": OPENWEATHERMAP_API_KEY, "units": "metric"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
