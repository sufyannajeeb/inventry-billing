"""Database engine and session factory.

The packaged app uses SQLite so it needs nothing installed on the target PC.
Set ``DATABASE_URL`` in ``.env`` to use PostgreSQL instead, e.g.::

    DATABASE_URL=postgresql+psycopg2://postgres:secret@localhost:5432/billing_system
"""

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

import app_paths

app_paths.load_env()


def _database_url():
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        return url
    return f"sqlite:///{app_paths.database_path().as_posix()}"


DATABASE_URL = _database_url()

_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    echo=(os.getenv("SQL_ECHO", "0").strip() == "1"),
    future=True,
    # SQLite connections are handed to Qt's thread pool, so relax the
    # single-thread check and wait briefly instead of failing on a busy file.
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, future=True)
Base = declarative_base()


def get_session():
    return SessionLocal()
