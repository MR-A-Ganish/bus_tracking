"""Bounded PostgreSQL pooling and one transaction per HTTP request."""
import atexit
import threading
from contextlib import contextmanager
from flask import g, has_request_context
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from config import DATABASE_URL

_pool = None
_pool_lock = threading.Lock()


def _open_connection():
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(DATABASE_URL, min_size=0, max_size=5, max_waiting=20,
                                   timeout=10, open=True,
                                   kwargs={"row_factory": dict_row, "connect_timeout": 10})
            atexit.register(_pool.close)
    return _pool.connection()


def _request_connection():
    if "db_connection" not in g:
        context = _open_connection()
        connection = context.__enter__()
        g.db_context = context
        g.db_connection = connection
    return g.db_connection


@contextmanager
def get_connection():
    if has_request_context():
        # Auth, business writes and notifications share a single transaction.
        # app.finish_transaction commits only after the whole request succeeds.
        yield _request_connection()
    else:
        with _open_connection() as connection:
            yield connection


def run_query(query, params=None, fetch=False, fetch_one=False, commit=False):
    auto_id = commit and query.strip().upper().startswith("INSERT") and "RETURNING" not in query.upper()
    if auto_id:
        query = query.rstrip().rstrip(";") + " RETURNING id"
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params or ())
            if fetch_one:
                result = cursor.fetchone()
            elif fetch:
                result = cursor.fetchall()
            elif auto_id:
                row = cursor.fetchone()
                result = row["id"] if row else None
            else:
                result = None
        if not has_request_context() and not commit:
            connection.rollback()
        return result
