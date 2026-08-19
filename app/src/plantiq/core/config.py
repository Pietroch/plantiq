# app/src/plantiq/core/config.py

import os

# Required — fails loud at import if missing
DATABASE_URL = os.environ["DATABASE_URL"]

# Optional: the web app runs fine without it, only the weather adapter needs it
OPENWEATHERMAP_API_KEY = os.environ.get("OPENWEATHERMAP_API_KEY", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
