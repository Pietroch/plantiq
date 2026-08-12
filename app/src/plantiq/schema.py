# app/src/plantiq/schema.py

from pathlib import Path

from plantiq.core.database import connect

# Resolved from the working directory — /app in the container, where db/ is mounted
SCHEMA_PATH = Path("db/schema.sql")


def run() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    # Single transaction: a failure mid-script leaves the database untouched
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)

    print(f"Schema applied from {SCHEMA_PATH}")


if __name__ == "__main__":
    run()
