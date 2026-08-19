# app/tests/conftest.py

import os

# Set before any import of plantiq.core.config, which reads os.environ at import
# time. Nothing here touches the network or the database.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("OPENWEATHERMAP_API_KEY", "test-key")
os.environ.setdefault("NTFY_TOPIC", "test-topic")
