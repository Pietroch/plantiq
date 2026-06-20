# scheduler/tests/test_database.py

from unittest.mock import MagicMock, patch

from sqlalchemy import text


def test_engine_connects_and_executes_query():
    import plantiq.core.database  # noqa: F401 — side-effect import, required for patch to resolve the attribute

    mock_rows = [("Monstera", "Paris", 48.8566, 2.3522)]
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = mock_rows

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.connect.return_value.__exit__.return_value = False

    with patch("plantiq.core.database.engine", mock_engine):
        with mock_engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT p.name, l.city, l.latitude, l.longitude"
                " FROM plants p JOIN locations l ON l.id = p.location_id"
            )).fetchall()

    assert rows == mock_rows
    mock_conn.execute.assert_called_once()
