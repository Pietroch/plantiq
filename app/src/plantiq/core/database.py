# app/src/plantiq/core/database.py

import psycopg
from psycopg.rows import dict_row

from plantiq.core.config import DATABASE_URL


def connect() -> psycopg.Connection:
    # Caller owns the connection — use as a context manager
    return psycopg.connect(DATABASE_URL)


def query(sql: str, params: tuple = (), *, fetch: str | None = None):
    # One connection per call — simple, no pool yet
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            if fetch == "all":
                return cur.fetchall()
            if fetch == "one":
                return cur.fetchone()
    return None
