#!/bin/bash
#
# Setup GCS Bucket for Bot Dashboard
#
# This script creates and configures the GCS bucket for storing:
# - Agent execution traces (with 90-day lifecycle)
# - Aggregated metrics data
#
# Prerequisites:
# - gcloud CLI installed and authenticated
# - Permissions: storage.buckets.create, storage.buckets.update
#
# Usage:
#   ./scripts/setup_gcs_bucket.sh

set -e  # Exit on error

PROJECT_ID="coderd"
BUCKET_NAME="bot-dashboard-vectorinstitute"
LOCATION="us-central1"

echo "=================================================="
echo "Setting up GCS bucket for Bot Dashboard"
echo "=================================================="
echo ""
echo "Project: $PROJECT_ID"
echo "Bucket: gs://$BUCKET_NAME"
echo "Location: $LOCATION"
echo ""

# Set active project
echo "Setting active GCP project..."
gcloud config set project "$PROJECT_ID"

# Check if bucket already exists
if gcloud storage buckets describe "gs://$BUCKET_NAME" &>/dev/null; then
    echo "✓ Bucket gs://$BUCKET_NAME already exists"
else
    echo "Creating GCS bucket..."
    gcloud storage buckets create "gs://$BUCKET_NAME" \
        --project="$PROJECT_ID" \
        --location="$LOCATION" \
        --uniform-bucket-level-access

    echo "✓ Bucket created successfully"
fi

# Apply lifecycle policy (90-day deletion for traces)
echo ""
echo "Applying lifecycle policy (90-day deletion for traces/)..."
gcloud storage buckets update "gs://$BUCKET_NAME" \
    --lifecycle-file="$(dirname "$0")/lifecycle-policy.json"

echo "✓ Lifecycle policy applied"

# Apply CORS policy for client-side fetches
echo ""
echo "Applying CORS policy..."
gcloud storage buckets update "gs://$BUCKET_NAME" \
    --cors-file="$(dirname "$0")/cors-policy.json"

echo "✓ CORS policy applied"

# Create directory structure
echo ""
echo "Creating directory structure..."
echo "" | gcloud storage cp - "gs://$BUCKET_NAME/data/.keep" || true
echo "" | gcloud storage cp - "gs://$BUCKET_NAME/traces/.keep" || true

echo "✓ Directory structure created"

# Set public read access for data files (dashboard needs to fetch them)
echo ""
echo "Setting public read access for data files..."
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET_NAME" \
    --member="allUsers" \
    --role="roles/storage.objectViewer"

echo "✓ Public read access granted"

# Display bucket info
echo ""
echo "=================================================="
echo "Bucket setup complete!"
echo "=================================================="
echo ""
echo "Bucket URL: https://storage.googleapis.com/$BUCKET_NAME"
echo ""
echo "Directory structure:"
echo "  gs://$BUCKET_NAME/data/          - Aggregated metrics (weekly updates)"
echo "  gs://$BUCKET_NAME/traces/        - Agent execution traces (90-day retention)"
echo ""
echo "Next steps:"
echo "1. Update GitHub Actions secrets if needed"
echo "2. Test trace upload from fix-remote-pr.yml workflow"
echo "3. Deploy dashboard to Cloud Run"
echo ""
