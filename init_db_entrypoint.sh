#!/bin/bash
# Entrypoint script that initializes the database before starting the application

set -e

echo "Starting ATS-Optimizer application..."

# Initialize database tables
echo "Initializing database tables..."
python3 -c "
from app.database import init_db
from app.models import Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    logger.info('Creating database tables...')
    init_db()
    logger.info('✓ Database tables created successfully')
except Exception as e:
    logger.error(f'✗ Failed to create tables: {e}')
    logger.error('Application will start but database operations will fail')
"

# Start the application
echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
