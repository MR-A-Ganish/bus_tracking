"""
Thin wrapper around mysql-connector-python.

Every route module calls get_connection() to get a live MySQL connection,
runs its query, and closes the connection. This keeps the code simple and
easy to explain in a project review (no ORM magic).
"""

import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG


def get_connection():
    """Return a new MySQL connection using the settings in config.py."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        raise RuntimeError(
            f"Could not connect to MySQL. Check backend/config.py DB_CONFIG "
            f"and make sure MySQL is running. Original error: {e}"
        )


def run_query(query, params=None, fetch=False, fetch_one=False, commit=False):
    """
    Convenience helper used throughout the routes/services layer.

    fetch      -> returns list of dict rows
    fetch_one  -> returns a single dict row (or None)
    commit     -> commits the transaction (for INSERT/UPDATE/DELETE)
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        result = None
        if fetch_one:
            result = cursor.fetchone()
        elif fetch:
            result = cursor.fetchall()
        if commit:
            conn.commit()
            result = cursor.lastrowid
        return result
    finally:
        cursor.close()
        conn.close()
