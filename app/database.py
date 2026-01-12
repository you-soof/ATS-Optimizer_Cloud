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
    # Priority 1: Explicit DATABASE_URL with full connection string (override all)
    # Check if DATABASE_URL is a complete connection string (not just using unix_socket)
    if DATABASE_URL:
        # If DATABASE_URL contains unix_socket, verify the socket path exists
        if "unix_socket=" in DATABASE_URL:
            import re
            socket_match = re.search(r'unix_socket=([^&\s]+)', DATABASE_URL)
            if socket_match:
                socket_path = socket_match.group(1)
                socket_dir = socket_path.split('/')[1] if '/' in socket_path else ''
                if socket_dir and not os.path.exists(f"/{socket_dir}"):
                    logger.warning(f"Unix socket path /{socket_dir} doesn't exist, falling back to CLOUD_SQL_CONNECTION_NAME logic")
                else:
                    logger.info("Using explicit DATABASE_URL with unix socket")
                    return DATABASE_URL
        else:
            # DATABASE_URL is a regular TCP connection (e.g., mysql+pymysql://user:pass@host:port/db)
            logger.info("Using explicit DATABASE_URL")
            return DATABASE_URL

    # Priority 2: Cloud Run → Cloud SQL (Unix socket) - only if socket dir exists
    if CLOUD_SQL_CONNECTION_NAME:
        unix_socket_dir = "/cloudsql"
        if os.path.exists(unix_socket_dir):
            unix_socket_path = f"{unix_socket_dir}/{CLOUD_SQL_CONNECTION_NAME}"
            connection_string = (
                f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@/"
                f"{DB_NAME}?unix_socket={unix_socket_path}"
            )
            logger.info(f"Using Cloud SQL socket: {CLOUD_SQL_CONNECTION_NAME}")
            return connection_string
        else:
            logger.warning(f"CLOUD_SQL_CONNECTION_NAME is set but {unix_socket_dir} doesn't exist")

    # Priority 3: SQLite fallback (local only)
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
