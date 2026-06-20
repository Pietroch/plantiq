# scheduler/tests/test_weather.py

from unittest.mock import MagicMock, patch

from plantiq.weather import get_weather


def test_get_weather_calls_owm_with_lat_lon():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "main": {"temp": 22.5},
        "weather": [{"description": "clear sky"}],
    }

    with patch("plantiq.weather.httpx.get", return_value=mock_response) as mock_get:
        result = get_weather(48.8566, 2.3522)

    mock_get.assert_called_once_with(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"lat": 48.8566, "lon": 2.3522, "appid": "test_owm_key", "units": "metric"},
        timeout=10,
    )
    assert result["main"]["temp"] == 22.5
    assert result["weather"][0]["description"] == "clear sky"
