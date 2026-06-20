# scheduler/tests/conftest.py

import os

# Set env vars before any module importing config.py is loaded
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost:5432/test"
os.environ["OPENWEATHERMAP_API_KEY"] = "test_owm_key"
os.environ["NTFY_TOPIC"] = "plantiq"
