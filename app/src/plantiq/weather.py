# app/src/plantiq/weather.py

from datetime import date, datetime
from zoneinfo import ZoneInfo

from plantiq.adapters.weather import current, normalise
from plantiq.core.database import query
from plantiq.core.logging import get_logger

log = get_logger(__name__)


def collect(batch_run_id: int | None = None) -> tuple[int, int]:
    """One call per open site. Returns (successes, failures)."""
    sites = query(
        "SELECT id, name, city, latitude, longitude, timezone "
        "FROM site WHERE closed_at IS NULL ORDER BY id",
        fetch="all",
    )
    done = failed = 0

    for site in sites:
        # A failure on one site must not stop the others: the batch is
        # per-site, never all-or-nothing
        try:
            raw = current(float(site["latitude"]), float(site["longitude"]))
            reading = normalise(raw)
            # observed_on in the site's own zone, never UTC — that is what
            # makes the daily uniqueness meaningful
            observed_on = reading["observed_at"].astimezone(ZoneInfo(site["timezone"])).date()

            query(
                """
                INSERT INTO weather_log
                       (site_id, batch_run_id, observed_at, observed_on,
                        temp_c, humidity_pct, cloud_pct, condition_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (site_id, observed_on) DO UPDATE SET
                    observed_at  = EXCLUDED.observed_at,
                    temp_c       = EXCLUDED.temp_c,
                    humidity_pct = EXCLUDED.humidity_pct,
                    cloud_pct    = EXCLUDED.cloud_pct,
                    condition_id = EXCLUDED.condition_id,
                    -- Shows the last run that refreshed the row, not the first
                    batch_run_id = EXCLUDED.batch_run_id,
                    fetched_at   = now()
                """,
                (
                    site["id"],
                    batch_run_id,
                    reading["observed_at"],
                    observed_on,
                    reading["temp_c"],
                    reading["humidity_pct"],
                    reading["cloud_pct"],
                    reading["condition_id"],
                ),
            )
            log.info(
                "%s : %.1f °C, %s %% humidité, %s %% nuages (%s)",
                site["city"] or site["name"],
                reading["temp_c"],
                reading["humidity_pct"],
                reading["cloud_pct"],
                observed_on,
            )
            done += 1
        except Exception:
            log.exception("Météo indisponible pour le site %s", site["name"])
            failed += 1

    return done, failed


def for_site(site_id: int, day: date | None = None) -> dict | None:
    """Today's reading for a site, or None.

    None is a normal answer, not an error: the rules must keep working
    without weather, with a neutral factor. An API outage must never
    silence every notification.
    """
    return query(
        "SELECT observed_at, observed_on, temp_c, humidity_pct, cloud_pct, condition_id "
        "FROM weather_log WHERE site_id = %s AND observed_on = %s",
        (site_id, day or _today(site_id)),
        fetch="one",
    )


def _today(site_id: int) -> date:
    zone = query("SELECT timezone FROM site WHERE id = %s", (site_id,), fetch="one")
    return datetime.now(ZoneInfo(zone["timezone"] if zone else "UTC")).date()


def run() -> None:
    done, failed = collect()
    print(f"\n{done} site(s) relevé(s), {failed} en échec.")


if __name__ == "__main__":
    run()
