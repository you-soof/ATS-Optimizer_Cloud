# ATS-Optimizer Database Connection Guide

## Current Issue: Cloud SQL Connection Timeout

Your Cloud SQL instance at `34.61.43.68` is timing out, which means:
- The public IP might not be configured for external access
- Firewall rules might be blocking your connection
- The instance might require authorized networks

## Solution Options

### Option 1: Enable Cloud SQL Public IP Access (For Local Development)

1. **Add your IP to authorized networks:**
```bash
# Get your public IP
curl ifconfig.me

# Add to Cloud SQL authorized networks
gcloud sql instances patch ats-cloud-database \
  --authorized-networks=YOUR_PUBLIC_IP/32 \
  --project=ats-optimizer-483812
```

2. **Update `.env` to use TCP:**
```env
DATABASE_URL=mysql+pymysql://ats_user:ats_password@34.61.43.68:3306/ats_db
```

3. **Restart Docker:**
```bash
docker stop ats-test
docker rm ats-test
docker run -d -p 8080:8080 --env-file .env --name ats-test ats-optimizer
```

### Option 2: Use SQLite for Local Development (Recommended for Testing)

1. **Copy the local environment file:**
```bash
cp .env.local .env
```

2. **Restart Docker:**
```bash
docker stop ats-test
docker rm ats-test
docker run -d -p 8080:8080 --env-file .env --name ats-test ats-optimizer
```

3. **Test the application:**
```bash
curl http://localhost:8080/health
curl http://localhost:8080/devices
```

This creates a local SQLite database file that doesn't require network access.

### Option 3: Deploy to Google Cloud Run (Production)

Cloud Run has direct access to Cloud SQL via Unix sockets. No public IP needed!

1. **Update `.env` for Cloud Run:**
```env
# Use Unix socket for Cloud Run
DATABASE_URL=mysql+pymysql://ats_user:ats_password@/ats_db?unix_socket=/cloudsql/ats-optimizer-483812:us-central1:ats-cloud-database
CLOUD_SQL_CONNECTION_NAME=ats-optimizer-483812:us-central1:ats-cloud-database
DB_USER=ats_user
DB_NAME=ats_db
DB_PASSWORD=ats_password
```

2. **Deploy to Cloud Run:**
```bash
# Build and push to Google Container Registry
gcloud builds submit --tag gcr.io/ats-optimizer-483812/ats-optimizer

# Deploy to Cloud Run with Cloud SQL connection
gcloud run deploy ats-optimizer \
  --image gcr.io/ats-optimizer-483812/ats-optimizer \
  --platform managed \
  --region us-central1 \
  --add-cloudsql-instances ats-optimizer-483812:us-central1:ats-cloud-database \
  --set-env-vars DATABASE_URL="mysql+pymysql://ats_user:ats_password@/ats_db?unix_socket=/cloudsql/ats-optimizer-483812:us-central1:ats-cloud-database" \
  --set-env-vars DB_USER=ats_user \
  --set-env-vars DB_NAME=ats_db \
  --set-env-vars DB_PASSWORD=ats_password \
  --allow-unauthenticated
```

### Option 4: Use Cloud SQL Proxy (Advanced Local Development)

Run Cloud SQL Proxy locally to connect to your Cloud SQL instance:

1. **Install Cloud SQL Proxy:**
```bash
# Download Cloud SQL Proxy
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.8.0/cloud-sql-proxy.linux.amd64
chmod +x cloud-sql-proxy
```

2. **Start the proxy:**
```bash
./cloud-sql-proxy --port 3306 ats-optimizer-483812:us-central1:ats-cloud-database &
```

3. **Update `.env` to use localhost:**
```env
DATABASE_URL=mysql+pymysql://ats_user:ats_password@localhost:3306/ats_db
```

4. **Run Docker with host network:**
```bash
docker run -d --network="host" --env-file .env --name ats-test ats-optimizer
```

## Testing Database Connection

Test which connection method works:

```bash
# Run connection test in Docker
docker run --rm --env-file .env ats-optimizer python3 tmp_rovodev_test_connection.py
```

## Verifying the Fix

After choosing an option, verify it works:

```bash
# Check logs
docker logs ats-test -f

# Test health endpoint
curl http://localhost:8080/health

# Test devices endpoint (should return empty array [])
curl http://localhost:8080/devices

# Check if tables were created
docker exec -it ats-test python3 -c "
from app.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text('SHOW TABLES'))
    tables = [row[0] for row in result]
    print('Tables:', tables)
"
```

## Troubleshooting

### Cloud SQL Public IP Not Working?

Check if public IP is enabled:
```bash
gcloud sql instances describe ats-cloud-database \
  --project=ats-optimizer-483812 \
  --format="get(ipAddresses[0].ipAddress)"
```

Enable public IP if needed:
```bash
gcloud sql instances patch ats-cloud-database \
  --assign-ip \
  --project=ats-optimizer-483812
```

### Firewall Issues?

Check authorized networks:
```bash
gcloud sql instances describe ats-cloud-database \
  --project=ats-optimizer-483812 \
  --format="get(settings.ipConfiguration.authorizedNetworks)"
```

Add your network:
```bash
gcloud sql instances patch ats-cloud-database \
  --authorized-networks=0.0.0.0/0 \
  --project=ats-optimizer-483812
```

⚠️ **Warning**: `0.0.0.0/0` allows access from anywhere. For production, use specific IP ranges.

### Still Can't Connect?

Use SQLite for local development:
```bash
# Use .env.local which falls back to SQLite
cp .env.local .env
docker stop ats-test && docker rm ats-test
docker run -d -p 8080:8080 --env-file .env --name ats-test ats-optimizer
```

## Summary of Changes Made

1. **Fixed `app/database.py`**: Improved connection logic to handle Unix socket vs TCP
2. **Updated `.env`**: Configured for TCP connection to Cloud SQL
3. **Created `.env.local`**: SQLite fallback for local development
4. **Enhanced error logging**: Better diagnostics in `app/main.py`
5. **Added entrypoint script**: `init_db_entrypoint.sh` ensures tables are created

## Recommended Workflow

**For Local Development:**
- Use SQLite (Option 2) - fastest and simplest
- Or use Cloud SQL Proxy (Option 4) - if you need production data

**For Production:**
- Deploy to Cloud Run (Option 3) - native Cloud SQL support via Unix sockets
- Tables are automatically created on first startup

## Next Steps

Choose the option that best fits your needs:
- 🏠 **Local dev/testing**: Use Option 2 (SQLite)
- 🚀 **Production deployment**: Use Option 3 (Cloud Run)
- 🔧 **Need real database locally**: Use Option 1 or 4

Would you like help with any of these options?
