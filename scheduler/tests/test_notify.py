# scheduler/tests/test_notify.py

from unittest.mock import MagicMock, patch

from plantiq.notify import send


def test_send_posts_to_ntfy():
    with patch("plantiq.notify.httpx.post", return_value=MagicMock()) as mock_post:
        send("Plantiq - Monstera", "Paris : 22°C, clear sky")

    mock_post.assert_called_once_with(
        "https://ntfy.sh/plantiq",
        content="Paris : 22°C, clear sky".encode("utf-8"),
        headers={
            "Title": "Plantiq - Monstera",
            "Content-Type": "text/plain; charset=utf-8",
        },
        timeout=10,
    )
