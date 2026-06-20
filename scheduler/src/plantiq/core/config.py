# scheduler/src/plantiq/core/config.py

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

# Supabase
DATABASE_URL = os.environ["DATABASE_URL"]

# OpenWeatherMap
OPENWEATHERMAP_API_KEY = os.environ["OPENWEATHERMAP_API_KEY"]

# ntfy
NTFY_TOPIC = os.environ["NTFY_TOPIC"]

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
