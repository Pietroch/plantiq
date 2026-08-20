# app/src/plantiq/restore.py

import json
import os
import sys
from pathlib import Path

from plantiq.core.database import connect

# Same mount point as backup.py; the Makefile maps the host folder onto it
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backups"))

# Foreign key order. Tables absent from the backup are skipped, so a file
# written before a table existed still restores cleanly.
TABLE_ORDER = [
    "material",
    "site",
    "species",
    "species_watering",
    "plant",
    "room",
    "room_version",
    "room_vertex",
    "wall_element",
    "container",
    "consumable",
    "tool",
    "plant_container",
    "plant_placement",
    # Before the three journals that carry batch_run_id, and so purged after them
    "batch_run",
    "weather_log",
    "care_log",
    "plant_health",
    "reminder",
    "notification_log",
]


def _latest_backup() -> Path:
    files = sorted(BACKUP_DIR.glob("plantiq_backup_*.json"))
    if not files:
        raise SystemExit(f"Aucune sauvegarde dans {BACKUP_DIR}")
    return files[-1]


def _schema_columns(cur, table: str) -> tuple[set[str], list[str]]:
    """Columns the table currently has, and those generated as identity."""
    cur.execute(
        "SELECT column_name, is_identity FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    )
    rows = cur.fetchall()
    return {name for name, _ in rows}, [name for name, identity in rows if identity == "YES"]


def _existing_tables(cur) -> set[str]:
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    return {row[0] for row in cur.fetchall()}


def run(path: Path | None = None) -> None:
    source = path or _latest_backup()
    payload = json.loads(source.read_text(encoding="utf-8"))
    tables = payload.get("tables", {})
    print(f"Source : {source}")
    print(f"Exportée le {payload.get('exported_at', '?')}\n")

    # A single transaction: a failure halfway leaves the database untouched
    with connect() as conn:
        with conn.cursor() as cur:
            present = _existing_tables(cur)
            restorable = [t for t in TABLE_ORDER if t in tables and t in present]

            # Reference rows seeded by schema.sql would collide with the backup,
            # so clear first, in reverse dependency order
            for table in reversed(restorable):
                cur.execute(f"DELETE FROM {table}")

            for table in restorable:
                rows = tables[table]
                columns, identities = _schema_columns(cur, table)
                if not rows:
                    print(f"{table:20}    0 ligne(s)")
                    continue

                # Columns dropped since the backup are ignored, so an added
                # column never blocks a restore
                kept = [column for column in rows[0] if column in columns]
                dropped = [column for column in rows[0] if column not in columns]
                override = "OVERRIDING SYSTEM VALUE " if identities else ""
                placeholders = ", ".join(["%s"] * len(kept))
                cur.executemany(
                    f"INSERT INTO {table} ({', '.join(kept)}) {override}VALUES ({placeholders})",
                    [tuple(row[column] for column in kept) for row in rows],
                )

                # Identity sequences keep counting from 1 unless realigned
                for column in identities:
                    cur.execute(
                        f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), "
                        f"COALESCE((SELECT max({column}) FROM {table}), 1))"
                    )

                note = f"  (colonnes ignorées : {', '.join(dropped)})" if dropped else ""
                print(f"{table:20} {len(rows):>4} ligne(s){note}")

    skipped = [t for t in tables if t not in TABLE_ORDER]
    if skipped:
        print(f"\nTables du fichier absentes de l'ordre de restauration : {', '.join(skipped)}")
    print("\nRestauration terminée.")


if __name__ == "__main__":
    run(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
