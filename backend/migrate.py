"""Apply tracked, transactional PostgreSQL migrations without resetting data."""
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from config import DATABASE_URL


def migrate():
    # Startup may import this module before Gunicorn forks worker processes.
    # A short-lived connection keeps migration sockets and pool threads out of workers.
    with psycopg.connect(DATABASE_URL,row_factory=dict_row,connect_timeout=10) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(72419628)")
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        for path in sorted((Path(__file__).resolve().parent.parent / "database" / "migrations").glob("*.sql")):
            if not conn.execute("SELECT 1 FROM schema_migrations WHERE name=%s", (path.name,)).fetchone():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations(name) VALUES (%s)", (path.name,))
                print(f"Applied {path.name}")


if __name__ == "__main__":
    migrate()
