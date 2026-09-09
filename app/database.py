"""Database helpers leveraging SQLModel."""
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, echo=False, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):  # pragma: no cover - driver hook
    """Enable WAL + a busy timeout so background workflow writes and dashboard
    polling reads can run concurrently without 'database is locked' errors."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def init_db() -> None:
    """Create database tables when the app starts."""

    SQLModel.metadata.create_all(engine)
    _ensure_columns()


def _ensure_columns() -> None:
    """`create_all` only creates missing *tables*, not missing columns on an
    already-existing sqlite file. Add columns introduced after the db file
    was first created, so existing local history keeps working."""

    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(workflows)"))}
        if "mode" not in existing:
            conn.execute(text("ALTER TABLE workflows ADD COLUMN mode VARCHAR DEFAULT 'multi_agentic'"))
            conn.commit()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""

    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
