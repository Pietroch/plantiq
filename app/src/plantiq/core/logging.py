# app/src/plantiq/core/logging.py

import logging


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # httpx logs the full request URL at INFO, which would print the
    # OpenWeatherMap key into the GitHub Actions log
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logging.getLogger(name)
