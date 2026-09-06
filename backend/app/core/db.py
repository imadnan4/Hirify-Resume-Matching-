"""Engine + session + init. pgvector attempted only on Postgres."""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
_is_memory = _is_sqlite and ":memory:" in settings.DATABASE_URL or settings.DATABASE_URL == "sqlite://"
connect_args = {"check_same_thread": False} if _is_sqlite else {}
pool_kw = {"poolclass": StaticPool} if _is_memory else {}
engine = create_engine(settings.DATABASE_URL, echo=settings.SQL_ECHO, connect_args=connect_args, **pool_kw)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db() -> None:
    from app import models  # noqa: F401  (register tables)

    if settings.DATABASE_URL.startswith(("postgresql", "postgres")):
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
