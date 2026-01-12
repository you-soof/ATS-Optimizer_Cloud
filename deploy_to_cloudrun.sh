#!/bin/bash
# Deploy ATS-Optimizer to Google Cloud Run

set -e

PROJECT_ID="ats-optimizer-483812"
SERVICE_NAME="ats-optimizer"
REGION="us-central1"
CLOUD_SQL_INSTANCE="ats-optimizer-483812:us-central1:ats-cloud-database"

echo "=========================================="
echo "Deploying ATS-Optimizer to Cloud Run"
echo "=========================================="

# Load environment variables
source .env.cloudrun

echo "1. Building and pushing container to Google Container Registry..."
gcloud builds submit --tag gcr.io/${PROJECT_ID}/${SERVICE_NAME} \
  --project=${PROJECT_ID}

echo ""
echo "2. Deploying to Cloud Run with Cloud SQL connection..."
gcloud run deploy ${SERVICE_NAME} \
  --image gcr.io/${PROJECT_ID}/${SERVICE_NAME} \
  --platform managed \
  --region ${REGION} \
  --project ${PROJECT_ID} \
  --add-cloudsql-instances ${CLOUD_SQL_INSTANCE} \
  --set-env-vars "DATABASE_URL=${DATABASE_URL}" \
  --set-env-vars "CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_CONNECTION_NAME}" \
  --set-env-vars "DB_USER=${DB_USER}" \
  --set-env-vars "DB_NAME=${DB_NAME}" \
  --set-env-vars "DB_PASSWORD=${DB_PASSWORD}" \
  --set-env-vars "FINGRID_API_KEY=${FINGRID_API_KEY}" \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 10 \
  --min-instances 0

echo ""
echo "=========================================="
echo "Deployment complete!"
echo "=========================================="

# Get the service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
  --region ${REGION} \
  --project ${PROJECT_ID} \
  --format 'value(status.url)')

echo ""
echo "Service URL: ${SERVICE_URL}"
echo ""
echo "Test endpoints:"
echo "  Health: ${SERVICE_URL}/health"
echo "  Devices: ${SERVICE_URL}/devices"
echo "  API Docs: ${SERVICE_URL}/docs"
echo ""
