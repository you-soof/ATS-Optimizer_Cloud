"""
Database configuration and session management
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import redis
from dotenv import load_dotenv

load_dotenv()

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ats_optimizer_dev.db")

# Create SQLAlchemy engine
# Use SQLite-friendly connect args when using a file-based SQLite URL
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # Verify connections before using
        pool_size=10,
        max_overflow=20,
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Redis connection
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI endpoints to get database session
    Usage: def endpoint(db: Session = Depends(get_db))
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_redis() -> redis.Redis:
    """
    Get Redis client for caching
    """
    return redis_client


def init_db():
    """
    Initialize database with tables
    Call this once during setup
    """
    from app.models import Base

    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created successfully")

    # Enable TimescaleDB extension (if using TimescaleDB)
    try:
        with engine.connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

            # Convert time-series tables to hypertables
            conn.execute(
                """
                SELECT create_hypertable('measurements', 'timestamp', 
                    if_not_exists => TRUE);
            """
            )
            conn.execute(
                """
                SELECT create_hypertable('price_data', 'timestamp', 
                    if_not_exists => TRUE);
            """
            )
            conn.execute(
                """
                SELECT create_hypertable('weather_forecasts', 'timestamp', 
                    if_not_exists => TRUE);
            """
            )
            conn.execute(
                """
                SELECT create_hypertable('grid_status', 'timestamp', 
                    if_not_exists => TRUE);
            """
            )
            conn.commit()
            print("✓ TimescaleDB hypertables created")
    except Exception as e:
        print(f"⚠ TimescaleDB setup skipped (not available or already configured): {e}")


def clear_cache():
    """
    Clear all Redis cache entries
    Useful for development/testing
    """
    redis_client.flushdb()
    print("✓ Redis cache cleared")
