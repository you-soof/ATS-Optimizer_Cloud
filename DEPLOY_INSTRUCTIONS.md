# Deployment Instructions for ATS-Optimizer

## 🎉 Local Testing Results

✅ **All tests passed!**
- Health endpoint working
- Device registration working  
- Database operations working
- Optimization endpoints working
- All API endpoints responding correctly

**Local test device registered:**
- Device ID: `test-device-001`
- Type: ASHP (Air Source Heat Pump)
- Location: Helsinki (60.17°N, 24.94°E)

---

## 🚀 Deploy to Google Cloud Run

### Option 1: Using Google Cloud Console (Web Interface)

1. **Go to Google Cloud Console**: https://console.cloud.google.com
2. **Select project**: `ats-optimizer-483812`
3. **Navigate to Cloud Run**: Menu > Cloud Run
4. **Click "Create Service"**
5. **Configure:**
   - Container image URL: Build from source (upload your code)
   - Service name: `ats-optimizer`
   - Region: `us-central1`
   - Authentication: Allow unauthenticated
   - CPU allocation: 1
   - Memory: 512 MiB
   - Maximum instances: 10
   - Timeout: 300 seconds

6. **Add Cloud SQL Connection:**
   - In the "Connections" tab
   - Add: `ats-optimizer-483812:us-central1:ats-cloud-database`

7. **Set Environment Variables:**
   ```
   DATABASE_URL=mysql+pymysql://ats_user:ats_password@/ats_db?unix_socket=/cloudsql/ats-optimizer-483812:us-central1:ats-cloud-database
   CLOUD_SQL_CONNECTION_NAME=ats-optimizer-483812:us-central1:ats-cloud-database
   DB_USER=ats_user
   DB_NAME=ats_db
   DB_PASSWORD=ats_password
   FINGRID_API_KEY=62ce8b01a88c4b949ab1b477cccacbb9
   ```

8. **Deploy!**

---

### Option 2: Using Google Cloud Shell (Recommended)

**Google Cloud Shell has gcloud CLI pre-installed!**

1. **Open Cloud Shell**: https://console.cloud.google.com (click the shell icon in top right)

2. **Clone or upload your code to Cloud Shell**
   ```bash
   # If you have the code in a git repo:
   git clone <your-repo-url>
   cd ats-optimizer
   
   # OR upload the files using the upload button in Cloud Shell
   ```

3. **Run the deployment script:**
   ```bash
   chmod +x deploy_to_cloudrun.sh
   ./deploy_to_cloudrun.sh
   ```

That's it! The script handles everything.

---

### Option 3: Install gcloud CLI Locally

If you want to deploy from your local machine:

**For macOS:**
```bash
# Install gcloud CLI
brew install google-cloud-sdk

# Initialize and authenticate
gcloud init
gcloud auth login

# Set project
gcloud config set project ats-optimizer-483812

# Deploy
./deploy_to_cloudrun.sh
```

**For Linux:**
```bash
# Install gcloud CLI
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Initialize and authenticate
gcloud init
gcloud auth login

# Set project
gcloud config set project ats-optimizer-483812

# Deploy
./deploy_to_cloudrun.sh
```

**For Windows:**
- Download installer: https://cloud.google.com/sdk/docs/install
- Run the installer
- Open a new terminal and run: `gcloud init`

---

### Option 4: Manual Deployment via Docker and GCR

If you prefer to build and push the Docker image manually:

```bash
# 1. Build the image locally
docker build -t ats-optimizer .

# 2. Tag for Google Container Registry
docker tag ats-optimizer gcr.io/ats-optimizer-483812/ats-optimizer

# 3. Configure Docker to use gcloud credentials
gcloud auth configure-docker

# 4. Push to GCR
docker push gcr.io/ats-optimizer-483812/ats-optimizer

# 5. Deploy from GCR
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
  --max-instances 10
```

---

## 🔍 After Deployment

### Get Service URL
```bash
gcloud run services describe ats-optimizer \
  --region us-central1 \
  --project ats-optimizer-483812 \
  --format 'value(status.url)'
```

### Test Deployment
```bash
# Replace <SERVICE_URL> with your actual service URL
SERVICE_URL="https://ats-optimizer-xxxxxxxxxx-uc.a.run.app"

# Test health
curl ${SERVICE_URL}/health

# Test devices
curl ${SERVICE_URL}/devices

# View API docs
open ${SERVICE_URL}/docs
```

### Monitor Logs
```bash
gcloud run logs tail ats-optimizer \
  --project ats-optimizer-483812 \
  --region us-central1
```

---

## 📦 What Gets Deployed

✅ **Application Features:**
- Device registration and management
- 24-hour optimization planning
- Real-time heat pump control recommendations
- Comfort risk analysis
- Demand response (VPP) capabilities
- Price and carbon intensity forecasts
- Integration with Fingrid and ENTSO-E APIs

✅ **Database:**
- Automatic table creation on first startup
- Cloud SQL connection via Unix socket
- Tables: devices, measurements, price_data, weather_forecasts, grid_status

✅ **Configuration:**
- Auto-scaling: 0 to 10 instances
- Cold start: ~5-10 seconds
- Timeout: 5 minutes
- Memory: 512 MiB
- Cost: Pay only when running

---

## 💰 Expected Costs

**Cloud Run (with minimal traffic):**
- Free tier: 2 million requests/month
- After free tier: ~$0.24 per million requests
- Expected: $0-5/month for development

**Cloud SQL (db-f1-micro):**
- ~$7-15/month (always running)
- Consider stopping when not in use for development

**Total estimated: $10-20/month for development**

---

## 🎯 Next Steps After Deployment

1. ✅ Test all endpoints with production URL
2. ✅ Register real devices
3. ✅ Monitor logs for any errors
4. ⚙️ Set up Cloud Scheduler for periodic updates (optional)
5. 🔒 Consider using Secret Manager for credentials (production)
6. 📊 Set up Cloud Monitoring alerts (production)
7. 🌐 Configure custom domain (optional)
8. 🔐 Add API authentication (production)

---

## 🆘 Need Help?

- **Cloud Run Docs**: https://cloud.google.com/run/docs
- **Cloud SQL Docs**: https://cloud.google.com/sql/docs
- **Troubleshooting Guide**: See `PRE_DEPLOYMENT_CHECKLIST.md`
- **API Documentation**: Once deployed, visit `<SERVICE_URL>/docs`

---

## ✅ Summary

**What we fixed:**
1. ❌ Database initialization errors → ✅ Auto-creation with fallback
2. ❌ Connection timeout issues → ✅ Smart connection logic
3. ❌ Environment variable problems → ✅ Proper configuration for local/cloud

**What we tested:**
- ✅ All API endpoints working locally
- ✅ Database operations successful
- ✅ Device registration and retrieval
- ✅ Optimization algorithms functioning
- ✅ External API integrations working

**Ready to deploy!** 🚀

Choose your preferred deployment method above and follow the steps.
