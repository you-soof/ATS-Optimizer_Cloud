import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import logging

logger = logging.getLogger(__name__)

# Get database configuration from environment
DATABASE_URL = os.getenv("DATABASE_URL")
CLOUD_SQL_CONNECTION_NAME = os.getenv("CLOUD_SQL_CONNECTION_NAME")  # Format: project:region:instance

def get_database_url():
    """
    Construct the appropriate database URL based on environment.
    
    Cloud Run uses Unix sockets to connect to Cloud SQL.
    Local development can use TCP connection with Cloud SQL Proxy or SQLite.
    """
    
    # If explicit DATABASE_URL is provided, use it (for local dev)
    if DATABASE_URL and not CLOUD_SQL_CONNECTION_NAME:
        logger.info(f"Using explicit DATABASE_URL: {DATABASE_URL.split('@')[0]}...")
        return DATABASE_URL
    
    # Cloud Run / Cloud SQL Unix Socket connection
    if CLOUD_SQL_CONNECTION_NAME:
        db_user = os.getenv("DB_USER", "root")
        db_password = os.getenv("DB_PASSWORD", "")
        db_name = os.getenv("DB_NAME", "ats-cloud-database")
        
        # Unix socket path in Cloud Run
        unix_socket_path = f"/cloudsql/{CLOUD_SQL_CONNECTION_NAME}"
        
        # Build connection string for Cloud SQL via Unix socket
        connection_string = (
            f"mysql+pymysql://{db_user}:{db_password}@/"
            f"{db_name}?unix_socket={unix_socket_path}"
        )
        
        logger.info(f"Using Cloud SQL connection: {CLOUD_SQL_CONNECTION_NAME}")
        return connection_string
    
    # Fallback to SQLite for local development
    logger.warning("No database configuration found, using SQLite fallback")
    return "sqlite:///./ats_optimizer_dev.db"


# Get the appropriate database URL
db_url = get_database_url()

# Create engine with appropriate settings
if db_url.startswith("sqlite"):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        echo=True,  # Set to False in production
    )
else:
    # MySQL/PostgreSQL configuration
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,  # Recycle connections after 1 hour
        connect_args={
            "connect_timeout": 10,
        },
        echo=False,  # Set to True for SQL debugging
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI endpoints to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    from app.models import Base
    
    try:
        logger.info("Initializing database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

# import os
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker, Session
# from typing import Generator

# DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ats_optimizer_dev.db")

# if DATABASE_URL.startswith("sqlite"):
#     engine = create_engine(
#         DATABASE_URL,
#         connect_args={"check_same_thread": False},
#         pool_pre_ping=True,
#     )
# else:
#     engine = create_engine(
#         DATABASE_URL,
#         pool_pre_ping=True,
#         pool_size=5,
#         max_overflow=10,
#         connect_args={"connect_timeout": 5},
#     )

# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# def get_db() -> Generator[Session, None, None]:
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()


