# scheduler/src/plantiq/run.py

from sqlalchemy import text

from plantiq.core.database import engine
from plantiq.core.logging import get_logger
from plantiq.notify import send
from plantiq.weather import get_weather

log = get_logger(__name__)


def run() -> None:
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT p.name, l.city, l.latitude, l.longitude"
            " FROM plants p"
            " JOIN locations l ON l.id = p.location_id"
        )).fetchall()

    log.info("Processing %d plants", len(rows))

    for name, city, lat, lon in rows:
        try:
            data = get_weather(lat, lon)
            temp = data["main"]["temp"]
            description = data["weather"][0]["description"]
            send(
                title=f"Plantiq - {name}",
                body=f"{city} : {temp:.0f}°C, {description}",
            )
        except Exception as e:
            log.error("Failed for plant %s (%s): %s", name, city, e)

    log.info("Scheduler run complete")


if __name__ == "__main__":
    run()
