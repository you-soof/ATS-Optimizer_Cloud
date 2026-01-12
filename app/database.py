import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
CLOUD_SQL_CONNECTION_NAME = os.getenv("CLOUD_SQL_CONNECTION_NAME")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

if not DB_NAME and not DATABASE_URL:
    raise RuntimeError("DB_NAME or DATABASE_URL must be set")

def get_database_url() -> str:
    # Explicit DATABASE_URL (local dev or manual override)
    if DATABASE_URL and not CLOUD_SQL_CONNECTION_NAME:
        logger.info("Using explicit DATABASE_URL")
        return DATABASE_URL

    # Cloud Run → Cloud SQL (Unix socket)
    if CLOUD_SQL_CONNECTION_NAME:
        unix_socket_path = f"/cloudsql/{CLOUD_SQL_CONNECTION_NAME}"
        connection_string = (
            f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@/"
            f"{DB_NAME}?unix_socket={unix_socket_path}"
        )
        logger.info(f"Using Cloud SQL socket: {CLOUD_SQL_CONNECTION_NAME}")
        return connection_string

    # SQLite fallback (local only)
    logger.warning("Using SQLite fallback database")
    return "sqlite:///./ats_optimizer_dev.db"


db_url = get_database_url()

if db_url.startswith("sqlite"):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        echo=False,
    )
else:
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        connect_args={"connect_timeout": 10},
        echo=False,
    )

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from app.models import Base

    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("✓ Database tables initialized successfully")
