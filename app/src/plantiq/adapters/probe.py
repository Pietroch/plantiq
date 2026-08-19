# app/src/plantiq/adapters/probe.py

"""Hits the real API once and lists every field it returns.

A discovery tool, not a regression test: it exists to decide what is worth
storing. Run it with `make weather`.
"""

import sys

from plantiq.adapters.weather import current, flatten, forecast
from plantiq.core.database import query


def _coordinates() -> tuple[float, float, str]:
    site = query(
        "SELECT name, city, latitude, longitude FROM site WHERE closed_at IS NULL ORDER BY id",
        fetch="one",
    )
    if site is None:
        raise SystemExit("Aucun site en base — en créer un d'abord.")
    return float(site["latitude"]), float(site["longitude"]), site["city"] or site["name"]


def _report(title: str, payload: dict, limit: int | None = None) -> None:
    fields = flatten(payload)
    shown = list(fields.items())[:limit] if limit else list(fields.items())
    print(f"\n=== {title} — {len(fields)} champ(s) ===\n")
    print(f"{'champ':38} {'type':10} valeur")
    print("-" * 88)
    for path, value in shown:
        print(f"{path:38} {type(value).__name__:10} {value}")
    if limit and len(fields) > limit:
        print(f"... {len(fields) - limit} champ(s) supplémentaires")


def run() -> None:
    lat, lon, label = _coordinates()
    print(f"Site : {label} ({lat}, {lon})")

    _report("Météo courante  /data/2.5/weather", current(lat, lon))

    if "--forecast" in sys.argv:
        # 40 three-hour steps: only the first is listed, the rest repeat its shape
        data = forecast(lat, lon)
        print(f"\nPrévisions : {data.get('cnt')} pas de 3 heures")
        _report("Prévisions  /data/2.5/forecast — premier pas", data["list"][0])


if __name__ == "__main__":
    run()
