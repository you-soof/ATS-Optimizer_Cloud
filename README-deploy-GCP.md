# Deploy `ats-optimizer` to Google Cloud (quick guide)

Prereqs:

- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- `docker` installed (if building locally)
- Billing enabled on your GCP project

High-level steps:

1. Enable required APIs

```
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com sqladmin.googleapis.com storage.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com iam.googleapis.com
```

2. Create Artifact Registry

```
gcloud artifacts repositories create ats-repo --repository-format=docker --location=us-central1
```

3. Build and push (recommended via Cloud Build)

```
gcloud builds submit --config=cloudbuild.yaml --substitutions=_COMMIT_SHA=latest
```

Alternate local build + push (requires Docker + auth):

```
# Build image locally
docker build -t us-central1-docker.pkg.dev/PROJECT_ID/ats-repo/ats-optimizer:latest .

# Configure docker to push to Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev
docker push us-central1-docker.pkg.dev/PROJECT_ID/ats-repo/ats-optimizer:latest
```

4. Deploy to Cloud Run (example)

```
gcloud run deploy ats-optimizer \
  --image us-central1-docker.pkg.dev/PROJECT_ID/ats-repo/ats-optimizer:latest \
  --region us-central1 \
  --platform managed \
  --add-cloudsql-instances=PROJECT_ID:us-central1:ats-sql \
  --set-env-vars PORT=8080,DB_HOST=/cloudsql/PROJECT_ID:us-central1:ats-sql \
  --service-account=SERVICE_ACCOUNT@PROJECT_ID.iam.gserviceaccount.com
```

5. Create Cloud SQL (Postgres) and Secret Manager entries

```
gcloud sql instances create ats-sql --database-version=POSTGRES_13 --region=us-central1
gcloud sql users set-password postgres --instance=ats-sql --password="YOUR_PASSWORD"
echo -n "YOUR_FINGRID_KEY" | gcloud secrets create FINGRID_API_KEY --data-file=-
```

6. Batch jobs & scheduling

Create a Cloud Run job (example) to run the processing entrypoint:

```
gcloud run jobs create process-data --image us-central1-docker.pkg.dev/PROJECT_ID/ats-repo/ats-optimizer:latest --region=us-central1 --execute-command "python" --execute-args "-u","app/optimization.py"
gcloud run jobs execute process-data --region=us-central1
```

Create a Cloud Scheduler job to trigger a URL or Pub/Sub topic on a schedule.

Notes / tips:

- Make sure `app/main.py` exposes an `app` callable and binds to `PORT` env var.
- Switch from SQLite to Postgres if currently using SQLite in `app/database.py`.
- Use Secret Manager for API keys and mount them into Cloud Run via `--set-secrets`.
- If you want me to actually run the `gcloud` steps, I need your project ID and an authenticated gcloud session on this machine (or you can run the commands shown).
