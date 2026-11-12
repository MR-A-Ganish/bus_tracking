"""Apply tracked, transactional PostgreSQL migrations without resetting data."""
from pathlib import Path
from database import get_connection


def migrate():
    with get_connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(72419628)")
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        for path in sorted((Path(__file__).resolve().parent.parent / "database" / "migrations").glob("*.sql")):
            if not conn.execute("SELECT 1 FROM schema_migrations WHERE name=%s", (path.name,)).fetchone():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations(name) VALUES (%s)", (path.name,))
                print(f"Applied {path.name}")


if __name__ == "__main__":
    migrate()
