# Pre-Deployment Checklist for Google Cloud Run

## ✅ Local Testing Complete

- [x] Application starts successfully with SQLite
- [x] All database tables created automatically
- [x] Health endpoint working (`/health`)
- [x] Device registration working (`/devices/register`)
- [x] Device listing working (`/devices`)
- [x] Daily optimization working (`/strategy/daily-plan`)
- [x] Current action endpoint working (`/strategy/current-action/{device_id}`)
- [x] Price/carbon forecast working (`/forecasts/price-carbon`)
- [x] Demand response working (`/grid/demand-response`)
- [x] API documentation accessible (`/docs`)

## 📋 Cloud Run Prerequisites

Before deploying, verify these are set up:

### 1. Google Cloud Project
```bash
# Verify project exists and you're authenticated
gcloud config get-value project
# Should show: ats-optimizer-483812

# If not, set it
gcloud config set project ats-optimizer-483812
```

### 2. Cloud SQL Instance
```bash
# Verify Cloud SQL instance exists
gcloud sql instances describe ats-cloud-database \
  --project=ats-optimizer-483812

# Verify database exists
gcloud sql databases list \
  --instance=ats-cloud-database \
  --project=ats-optimizer-483812
```

### 3. Enable Required APIs
```bash
# Enable Cloud Run API
gcloud services enable run.googleapis.com --project=ats-optimizer-483812

# Enable Cloud Build API
gcloud services enable cloudbuild.googleapis.com --project=ats-optimizer-483812

# Enable Container Registry API
gcloud services enable containerregistry.googleapis.com --project=ats-optimizer-483812

# Enable Cloud SQL Admin API
gcloud services enable sqladmin.googleapis.com --project=ats-optimizer-483812
```

### 4. Cloud SQL User and Database
```bash
# Connect to Cloud SQL and verify user/database
gcloud sql connect ats-cloud-database --user=root --project=ats-optimizer-483812

# Once connected, run these SQL commands:
# CREATE DATABASE IF NOT EXISTS ats_db;
# CREATE USER IF NOT EXISTS 'ats_user'@'%' IDENTIFIED BY 'ats_password';
# GRANT ALL PRIVILEGES ON ats_db.* TO 'ats_user'@'%';
# FLUSH PRIVILEGES;
# EXIT;
```

### 5. Service Account Permissions
```bash
# The Cloud Run service will need Cloud SQL Client permissions
# This is usually set automatically, but verify:
PROJECT_NUMBER=$(gcloud projects describe ats-optimizer-483812 --format="value(projectNumber)")
echo "Project number: ${PROJECT_NUMBER}"

gcloud projects add-iam-policy-binding ats-optimizer-483812 \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

## 🚀 Deployment Steps

### Option 1: Automated Deployment (Recommended)
```bash
./deploy_to_cloudrun.sh
```

### Option 2: Manual Deployment
```bash
# 1. Build and push image
gcloud builds submit --tag gcr.io/ats-optimizer-483812/ats-optimizer

# 2. Deploy to Cloud Run
gcloud run deploy ats-optimizer \
  --image gcr.io/ats-optimizer-483812/ats-optimizer \
  --platform managed \
  --region us-central1 \
  --project ats-optimizer-483812 \
  --add-cloudsql-instances ats-optimizer-483812:us-central1:ats-cloud-database \
  --set-env-vars DATABASE_URL="mysql+pymysql://ats_user:ats_password@/ats_db?unix_socket=/cloudsql/ats-optimizer-483812:us-central1:ats-cloud-database" \
  --set-env-vars CLOUD_SQL_CONNECTION_NAME="ats-optimizer-483812:us-central1:ats-cloud-database" \
  --set-env-vars DB_USER=ats_user \
  --set-env-vars DB_NAME=ats_db \
  --set-env-vars DB_PASSWORD=ats_password \
  --set-env-vars FINGRID_API_KEY=62ce8b01a88c4b949ab1b477cccacbb9 \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 10 \
  --min-instances 0
```

## ✅ Post-Deployment Verification

After deployment completes, test these endpoints:

```bash
# Get the service URL
SERVICE_URL=$(gcloud run services describe ats-optimizer \
  --region us-central1 \
  --project ats-optimizer-483812 \
  --format 'value(status.url)')

echo "Service URL: ${SERVICE_URL}"

# Test health endpoint
curl ${SERVICE_URL}/health

# Test devices endpoint
curl ${SERVICE_URL}/devices

# Register a test device
curl -X POST ${SERVICE_URL}/devices/register \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "prod-device-001",
    "name": "Production Heat Pump",
    "latitude": 60.1699,
    "longitude": 24.9384,
    "insulation_level": "medium",
    "floor_area": 100.0,
    "volume": 250.0,
    "thermal_mass": 50000.0,
    "heat_pump_type": "ASHP",
    "rated_power": 5.0,
    "cop_rating": 3.5,
    "comfort_min_temp": 20.0,
    "comfort_max_temp": 23.0,
    "vpp_enabled": true
  }'

# View API documentation
echo "API Docs: ${SERVICE_URL}/docs"
```

## 📊 Monitoring

### Check Logs
```bash
# View recent logs
gcloud run logs read ats-optimizer \
  --project ats-optimizer-483812 \
  --region us-central1 \
  --limit 50

# Follow logs in real-time
gcloud run logs tail ats-optimizer \
  --project ats-optimizer-483812 \
  --region us-central1
```

### Check Service Status
```bash
gcloud run services describe ats-optimizer \
  --project ats-optimizer-483812 \
  --region us-central1
```

## 🔧 Troubleshooting

### If deployment fails:
1. Check logs: `gcloud run logs read ats-optimizer --limit 50`
2. Verify Cloud SQL instance is running
3. Verify database credentials in .env.cloudrun
4. Check IAM permissions for service account

### If database connection fails:
1. Verify Cloud SQL connection name is correct
2. Check that Cloud SQL instance is in the same region
3. Verify database user has proper permissions
4. Check Cloud Run service has `cloudsql.client` role

### If tables don't exist:
- The `init_db_entrypoint.sh` script should create tables automatically on startup
- Check logs for any errors during initialization
- Tables can be created manually if needed (see DEPLOYMENT_GUIDE.md)

## 🎉 Success Criteria

Your deployment is successful when:
- [ ] Health endpoint returns `{"status": "healthy"}`
- [ ] `/devices` endpoint returns `[]` or list of devices
- [ ] `/docs` shows interactive API documentation
- [ ] Device registration works
- [ ] No database connection errors in logs
- [ ] Service URL is accessible

## 📝 Notes

- **Cold starts**: First request may take 5-10 seconds
- **Min instances**: Set to 0 to save costs (only pay when running)
- **Scaling**: Auto-scales from 0 to 10 instances based on traffic
- **Timeout**: 300 seconds for optimization requests
- **Memory**: 512Mi should be sufficient for typical workloads

## 🔐 Security Reminders

- [ ] Don't commit .env files to git
- [ ] Rotate database passwords regularly
- [ ] Consider using Secret Manager for sensitive data
- [ ] Review IAM permissions periodically
- [ ] Enable Cloud Armor for DDoS protection (optional)
