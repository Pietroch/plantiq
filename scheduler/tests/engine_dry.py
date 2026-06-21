# scheduler/tests/engine_dry.py

from datetime import datetime

import plantiq.engine as eng
from plantiq.engine import (
    TZ,
    _rule_fertilizing,
    _rule_health_check,
    _rule_misting,
    _rule_repotting,
    _rule_watering,
    _rule_weather_warning,
)


def run_dry(plant, profile, plant_location, container, accessories, health, care_logs, weather) -> list[dict]:
    """
    Run all engine rules against the provided dicts.
    Returns a list of notification dicts that would have been sent.
    No DB write. No ntfy call.
    """
    today = datetime.now(TZ).date()
    notifications = []

    class MockConn:
        def execute(self, *a, **kw): pass
        def commit(self): pass
        def rollback(self): pass

    original_send = eng.send

    def capture_send(title, body):
        notifications.append({"title": title, "body": body})

    eng.send = capture_send

    try:
        conn = MockConn()
        last_notifs = {}  # no prior notifications — all rules can fire

        snoozes = set()  # simulation — no active snoozes
        _rule_weather_warning(conn, plant, profile, plant_location, weather, health, last_notifs, snoozes, today, TZ)
        _rule_health_check(conn, plant, health, last_notifs, snoozes, today, TZ)
        _rule_repotting(conn, plant, profile, container, health, last_notifs, snoozes, today, TZ)
        _rule_watering(conn, plant, profile, plant_location, container, accessories, health, weather, care_logs, last_notifs, snoozes, today, TZ)
        _rule_misting(conn, plant, profile, plant_location, container, health, weather, care_logs, last_notifs, snoozes, today, TZ)
        _rule_fertilizing(conn, plant, profile, container, health, care_logs, last_notifs, snoozes, today, TZ)
    finally:
        eng.send = original_send  # always restore

    return notifications
