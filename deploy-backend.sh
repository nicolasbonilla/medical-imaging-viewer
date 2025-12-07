#!/bin/bash

# ============================================================================
# Deploy Backend to Google Cloud Run
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Medical Imaging Viewer - Backend Deploy${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI not found${NC}"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if user is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
    echo -e "${YELLOW}Authenticating with Google Cloud...${NC}"
    gcloud auth login
fi

# Get project ID
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: No Google Cloud project set${NC}"
    echo "Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo -e "${GREEN}Project ID: ${PROJECT_ID}${NC}"
echo ""

# Configuration
SERVICE_NAME="medical-imaging-backend"
REGION="us-central1"
MEMORY="2Gi"
CPU="2"
TIMEOUT="300"
MAX_INSTANCES="10"

# Navigate to backend directory
cd backend

# Check if .env.production exists
if [ ! -f ".env.production" ]; then
    echo -e "${YELLOW}Warning: .env.production not found${NC}"
    echo "Creating from .env.example..."
    cp .env.example .env.production
    echo -e "${RED}IMPORTANT: Edit .env.production with production values before deploying!${NC}"
    read -p "Press Enter to continue or Ctrl+C to cancel..."
fi

# Enable required APIs
echo -e "${YELLOW}Enabling required APIs...${NC}"
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com

# Build and deploy
echo -e "${YELLOW}Building and deploying to Cloud Run...${NC}"
echo "This may take several minutes..."
echo ""

gcloud run deploy $SERVICE_NAME \
  --source . \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory $MEMORY \
  --cpu $CPU \
  --timeout $TIMEOUT \
  --max-instances $MAX_INSTANCES \
  --quiet

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region $REGION \
  --format 'value(status.url)')

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Successful!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Backend URL: ${GREEN}${SERVICE_URL}${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Update frontend/.env.production with backend URL:"
echo "   VITE_API_BASE_URL=${SERVICE_URL}"
echo ""
echo "2. Update backend CORS_ORIGINS to include frontend URL"
echo ""
echo "3. Test the backend health endpoint:"
echo "   curl ${SERVICE_URL}/api/health"
echo ""
echo -e "${YELLOW}View logs:${NC}"
echo "   gcloud run logs read $SERVICE_NAME --region $REGION --limit 50"
echo ""
echo -e "${YELLOW}Update environment variables:${NC}"
echo "   gcloud run services update $SERVICE_NAME --region $REGION --update-env-vars KEY=VALUE"
echo ""

# Test health endpoint
echo -e "${YELLOW}Testing health endpoint...${NC}"
if curl -s "${SERVICE_URL}/api/health" | grep -q "healthy"; then
    echo -e "${GREEN}✓ Backend is healthy${NC}"
else
    echo -e "${RED}✗ Backend health check failed${NC}"
    echo "Check logs: gcloud run logs read $SERVICE_NAME --region $REGION --limit 50"
fi

cd ..
