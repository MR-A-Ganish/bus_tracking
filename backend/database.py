"""
Thin wrapper around psycopg2 (PostgreSQL).

Every route module calls get_connection() to get a live Postgres connection,
runs its query, and closes the connection. This keeps the code simple and
easy to explain in a project review (no ORM magic).
"""

import psycopg2
import psycopg2.extras
from config import DB_CONFIG


def get_connection():
    """Return a new PostgreSQL connection using the settings in config.py."""
    try:
        if "dsn" in DB_CONFIG:
            conn = psycopg2.connect(DB_CONFIG["dsn"])
        else:
            conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        raise RuntimeError(
            f"Could not connect to PostgreSQL. Check backend/config.py DB_CONFIG "
            f"and make sure the database is running. Original error: {e}"
        )


def run_query(query, params=None, fetch=False, fetch_one=False, commit=False):
    """
    Convenience helper used throughout the routes/services layer.

    fetch      -> returns list of dict rows
    fetch_one  -> returns a single dict row (or None)
    commit     -> commits the transaction (for INSERT/UPDATE/DELETE). For a
                  plain INSERT with no explicit RETURNING clause, the new
                  row's id is returned (mirrors mysql-connector's lastrowid,
                  which every INSERT call site in this codebase relies on).
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        appended_returning = False
        if commit and query.strip().upper().startswith("INSERT") and "RETURNING" not in query.upper():
            query = query.rstrip().rstrip(";") + " RETURNING id"
            appended_returning = True

        cursor.execute(query, params or ())

        result = None
        if fetch_one:
            result = cursor.fetchone()
        elif fetch:
            result = cursor.fetchall()
        elif appended_returning:
            row = cursor.fetchone()
            result = row["id"] if row else None

        if commit:
            conn.commit()
        return result
    finally:
        cursor.close()
        conn.close()
