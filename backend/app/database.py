"""SQLAlchemy engine + session + declarative base."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

_is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)

if _is_sqlite:
    # WAL + a generous busy timeout let concurrent requests (multiple department
    # logins, agent calls, back-to-back generates) write without "database is
    # locked" 500s. Without this, a locked write raises mid-request and the error
    # response skips the CORS middleware, surfacing in the browser as a CORS/network
    # failure rather than a clean error.
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
