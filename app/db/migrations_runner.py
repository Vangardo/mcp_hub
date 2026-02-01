import sqlite3
from pathlib import Path
from app.db.database import db


MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"
BASELINE_MIGRATION = "001_init.sql"


def get_applied_migrations(conn: sqlite3.Connection) -> set:
    try:
        cursor = conn.execute(
            "SELECT name FROM schema_migrations ORDER BY name"
        )
        return {row["name"] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        return set()


def create_migrations_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def get_existing_tables(conn: sqlite3.Connection) -> set:
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    tables = {row["name"] for row in cursor.fetchall()}
    tables.discard("schema_migrations")
    tables.discard("sqlite_sequence")
    return tables


def mark_migrations_as_applied(conn: sqlite3.Connection, migration_files: list[Path]):
    for migration_file in migration_files:
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (name) VALUES (?)",
            (migration_file.name,),
        )
    conn.commit()


def run_migrations():
    conn = db.connect()
    create_migrations_table(conn)

    applied = get_applied_migrations(conn)
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    existing_tables = get_existing_tables(conn)

    if not applied:
        baseline = next(
            (migration for migration in migration_files if migration.name == BASELINE_MIGRATION),
            None,
        )
        if baseline and not existing_tables:
            print(f"Applying baseline migration: {baseline.name}")
            sql = baseline.read_text()
            try:
                conn.executescript(sql)
                mark_migrations_as_applied(conn, migration_files)
                print(f"Baseline {baseline.name} applied successfully")
                return
            except Exception as e:
                conn.rollback()
                raise RuntimeError(f"Baseline migration {baseline.name} failed: {e}")

        if existing_tables:
            print("Existing tables detected without schema_migrations; marking migrations as applied.")
            mark_migrations_as_applied(conn, migration_files)
            return

    for migration_file in migration_files:
        migration_name = migration_file.name
        if migration_name in applied:
            continue

        print(f"Applying migration: {migration_name}")
        sql = migration_file.read_text()

        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (name) VALUES (?)",
                (migration_name,)
            )
            conn.commit()
            print(f"Migration {migration_name} applied successfully")
        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Migration {migration_name} failed: {e}")
