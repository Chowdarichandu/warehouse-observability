import hashlib
from pathlib import Path

from obs.db import connection


def migrate() -> None:
    directory = Path(__file__).resolve().parents[2] / "sql" / "migrations"
    if not directory.exists():
        directory = Path("/app/sql/migrations")
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(110527)")
        conn.execute("CREATE SCHEMA IF NOT EXISTS obs")
        conn.execute("""CREATE TABLE IF NOT EXISTS obs.schema_migrations
            (name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz DEFAULT now())""")
        for path in sorted(directory.glob("*.sql")):
            content = path.read_text()
            checksum = hashlib.sha256(content.encode()).hexdigest()
            applied = conn.execute(
                "SELECT checksum FROM obs.schema_migrations WHERE name=%s", (path.name,)
            ).fetchone()
            if applied:
                if applied["checksum"] != checksum:
                    raise RuntimeError(f"Applied migration changed: {path.name}")
                continue
            conn.execute(content)
            conn.execute(
                "INSERT INTO obs.schema_migrations(name, checksum) VALUES (%s,%s)",
                (path.name, checksum),
            )
            print(f"Applied {path.name}")


if __name__ == "__main__":
    migrate()
