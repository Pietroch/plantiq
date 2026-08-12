# app/src/plantiq/core/config.py

import os

# Required — fails loud at import if missing
DATABASE_URL = os.environ["DATABASE_URL"]
