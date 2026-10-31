import logging
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import settings

logger = logging.getLogger("jobshield.db")

connect_args = {}
if "sqlite" in settings.DATABASE_URL:
    connect_args["check_same_thread"] = False
elif "psycopg" in settings.DATABASE_URL:
    # 5-second timeout on connect to prevent hanging connections
    connect_args["connect_timeout"] = 5

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a database session and safely closing it after the request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
