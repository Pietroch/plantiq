# scheduler/src/plantiq/backup.py

import datetime
import decimal
import json
import os
import uuid
from pathlib import Path

from sqlalchemy import text

from plantiq.core.database import engine as db_engine
from plantiq.core.logging import get_logger

log = get_logger(__name__)

TABLES = [
    "locations",
    "plants",
    "plant_profile",
    "plant_location",
    "plant_container",
    "plant_accessories",
    "plant_health",
    "care_logs",
    "notifications_log",
    "notification_snooze",
    "weather_logs",
]


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return super().default(obj)


def run() -> None:
    today = datetime.date.today().isoformat()
    filename = f"plantiq_backup_{today}.json"

    backup_dir = os.environ.get("BACKUP_PATH", ".")
    output_path = Path(backup_dir) / filename

    output_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {
        "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tables": {},
    }

    with db_engine.connect() as conn:
        for table in TABLES:
            rows = conn.execute(text(f"SELECT * FROM {table}")).mappings().fetchall()
            data["tables"][table] = [dict(r) for r in rows]
            log.info("Exported %d rows from %s", len(rows), table)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, cls=_Encoder, ensure_ascii=False, indent=2)

    print(f"Backup written to: {output_path.resolve()}")


if __name__ == "__main__":
    run()
