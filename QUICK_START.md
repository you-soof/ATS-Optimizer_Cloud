# 🚀 ATS-Optimizer Quick Start

## Local Development (Working Now!)

```bash
# Start the application
docker run -d -p 8080:8080 --env-file .env.local --name ats-local ats-optimizer

# Test it
curl http://localhost:8080/health

# View API docs
open http://localhost:8080/docs

# Stop when done
docker stop ats-local
```

---

## Deploy to Google Cloud Run

### Method 1: Cloud Shell (Recommended - Takes 5 minutes)
```bash
# 1. Open Cloud Shell at https://console.cloud.google.com
# 2. Upload your code
# 3. Run:
./deploy_to_cloudrun.sh
```

### Method 2: Cloud Console (No CLI needed)
1. Go to https://console.cloud.google.com/run
2. Click "Create Service"
3. Upload source code
4. Set environment variables from `.env.cloudrun`
5. Add Cloud SQL connection: `ats-optimizer-483812:us-central1:ats-cloud-database`
6. Deploy!

---

## After Deployment

```bash
# Get your service URL
SERVICE_URL="<your-cloud-run-url>"

# Test health
curl ${SERVICE_URL}/health

# Register a device
curl -X POST ${SERVICE_URL}/devices/register \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "my-heatpump-001",
    "name": "My Heat Pump",
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

# Get optimization plan
curl -X POST ${SERVICE_URL}/strategy/daily-plan \
  -H "Content-Type: application/json" \
  -d '{"device_id": "my-heatpump-001"}'
```

---

## 📚 Full Documentation

- **DEPLOYMENT_SUMMARY.md** - Complete overview of what was fixed
- **DEPLOY_INSTRUCTIONS.md** - Detailed deployment steps
- **PRE_DEPLOYMENT_CHECKLIST.md** - Prerequisites checklist
- **DEPLOYMENT_GUIDE.md** - Comprehensive guide

---

## 🎯 Key API Endpoints

| Endpoint | What it does |
|----------|-------------|
| `GET /health` | Check service health |
| `POST /devices/register` | Register a heat pump |
| `GET /devices` | List all devices |
| `POST /strategy/daily-plan` | Get 24-hour optimization |
| `GET /strategy/current-action/{id}` | What to do RIGHT NOW |
| `POST /analytics/comfort-risk` | Analyze comfort risk |
| `POST /grid/demand-response` | VPP demand response |
| `GET /forecasts/price-carbon` | Price & carbon forecast |
| `GET /docs` | Interactive API docs |

---

## ✅ Status: READY TO DEPLOY! 🚀

Everything is tested and working. Choose your deployment method above!
