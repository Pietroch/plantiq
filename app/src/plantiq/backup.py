# app/src/plantiq/backup.py

import datetime
import decimal
import json
import os
from pathlib import Path

from plantiq.core.database import query

# Fixed mount point inside the container; the Makefile maps the host folder onto it
OUTPUT_DIR = Path(os.environ.get("BACKUP_DIR", "/backups"))


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime | datetime.date):
            return obj.isoformat()
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return super().default(obj)


def _table_names() -> list[str]:
    # Read from the catalogue rather than a hardcoded list: the schema still moves,
    # and a forgotten table would silently drop out of every backup.
    rows = query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "ORDER BY table_name",
        fetch="all",
    )
    return [row["table_name"] for row in rows]


def run() -> None:
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    # Same prefix as the earlier backups; the time keeps two runs a day apart
    output = OUTPUT_DIR / f"plantiq_backup_{stamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {"exported_at": datetime.datetime.now(datetime.UTC).isoformat(), "tables": {}}
    for table in _table_names():
        rows = query(f"SELECT * FROM {table}", fetch="all")
        data["tables"][table] = [dict(row) for row in rows]
        print(f"{table:20} {len(rows):>4} ligne(s)")

    with open(output, "w", encoding="utf-8") as handle:
        json.dump(data, handle, cls=_Encoder, ensure_ascii=False, indent=2)

    print(f"\nSauvegarde écrite dans {output}")


if __name__ == "__main__":
    run()
