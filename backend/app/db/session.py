from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

_connect_args: dict = {}
_engine_kwargs: dict = {"pool_pre_ping": True, "future": True}
if _settings.is_sqlite:
    _connect_args = {"check_same_thread": False}
    _engine_kwargs["pool_pre_ping"] = False
else:
    if _settings.database_url.startswith(("postgresql:", "postgresql+")):
        _connect_args = {"connect_timeout": 5}
    _engine_kwargs["pool_timeout"] = 5
    _engine_kwargs["pool_size"] = _settings.database_pool_size
    _engine_kwargs["max_overflow"] = _settings.database_max_overflow

engine: Engine = create_engine(
    _settings.database_url,
    echo=_settings.sql_echo,
    connect_args=_connect_args,
    **_engine_kwargs,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
    if not _settings.is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Unit-of-work for background tasks and services outside a request."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
