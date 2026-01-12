FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY . .

# Copy and set permissions for entrypoint script
COPY init_db_entrypoint.sh /app/init_db_entrypoint.sh
RUN chmod +x /app/init_db_entrypoint.sh

# Expose port
EXPOSE 8080
ENV PORT=8080

# Use entrypoint script that initializes DB before starting the app
CMD ["/app/init_db_entrypoint.sh"]