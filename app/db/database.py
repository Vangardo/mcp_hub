import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from app.settings import settings


class Database:
    _instance: Optional["Database"] = None
    _connection: Optional[sqlite3.Connection] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def connect(self) -> sqlite3.Connection:
        if self._connection is None:
            db_path = Path(settings.database_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                str(db_path),
                check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    def close(self):
        if self._connection:
            self._connection.close()
            self._connection = None


db = Database()


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = db.connect()
    try:
        yield conn
    finally:
        pass


def init_db():
    from app.db.migrations_runner import run_migrations
    run_migrations()
