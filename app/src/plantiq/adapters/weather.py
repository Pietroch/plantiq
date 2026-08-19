# app/src/plantiq/adapters/weather.py

from datetime import UTC, datetime

import httpx

from plantiq.core.config import OPENWEATHERMAP_API_KEY

CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
TIMEOUT = 10


def _call(url: str, lat: float, lon: float) -> dict:
    if not OPENWEATHERMAP_API_KEY:
        raise RuntimeError("OPENWEATHERMAP_API_KEY absente de l'environnement.")
    response = httpx.get(
        url,
        params={
            "lat": lat,
            "lon": lon,
            "appid": OPENWEATHERMAP_API_KEY,
            "units": "metric",
            "lang": "fr",
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def current(lat: float, lon: float) -> dict:
    """Raw current-weather payload. No normalisation yet: the fields are still being chosen."""
    return _call(CURRENT_URL, lat, lon)


def forecast(lat: float, lon: float) -> dict:
    """Raw five-day forecast, three-hour steps."""
    return _call(FORECAST_URL, lat, lon)


def normalise(raw: dict) -> dict:
    """Raw payload into the five stored fields.

    The only place that knows the OpenWeatherMap shape: weather[0].id,
    clouds.all, and dt as a Unix timestamp. Everything downstream sees
    plain names and never touches the provider format.
    """
    main = raw.get("main") or {}
    condition = (raw.get("weather") or [{}])[0]
    return {
        "observed_at": datetime.fromtimestamp(raw["dt"], tz=UTC),
        "temp_c": main.get("temp"),
        "humidity_pct": main.get("humidity"),
        "cloud_pct": (raw.get("clouds") or {}).get("all"),
        "condition_id": condition.get("id"),
    }


def flatten(payload, prefix: str = "") -> dict[str, object]:
    """Nested payload into dotted paths, so every field can be listed and compared."""
    flat: dict[str, object] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            flat.update(flatten(value, f"{prefix}.{key}" if prefix else key))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            flat.update(flatten(value, f"{prefix}[{index}]"))
    else:
        flat[prefix] = payload
    return flat
