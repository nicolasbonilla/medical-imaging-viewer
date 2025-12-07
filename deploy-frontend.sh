#!/bin/bash

# ============================================================================
# Deploy Frontend to Firebase Hosting
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Medical Imaging Viewer - Frontend Deploy${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if firebase CLI is installed
if ! command -v firebase &> /dev/null; then
    echo -e "${RED}Error: Firebase CLI not found${NC}"
    echo "Install: npm install -g firebase-tools"
    exit 1
fi

# Check if node is installed
if ! command -v node &> /dev/null; then
    echo -e "${RED}Error: Node.js not found${NC}"
    echo "Install from: https://nodejs.org/"
    exit 1
fi

# Check if user is authenticated
if ! firebase projects:list &> /dev/null; then
    echo -e "${YELLOW}Authenticating with Firebase...${NC}"
    firebase login
fi

# Get project ID from .firebaserc
if [ ! -f ".firebaserc" ]; then
    echo -e "${RED}Error: .firebaserc not found${NC}"
    echo "Run: firebase use --add"
    exit 1
fi

PROJECT_ID=$(grep -oP '"default":\s*"\K[^"]+' .firebaserc)
echo -e "${GREEN}Project ID: ${PROJECT_ID}${NC}"
echo ""

# Navigate to frontend directory
cd frontend

# Check if .env.production exists
if [ ! -f ".env.production" ]; then
    echo -e "${YELLOW}Warning: .env.production not found${NC}"
    echo "Creating template..."
    echo "VITE_API_BASE_URL=https://YOUR-BACKEND-URL" > .env.production
    echo -e "${RED}IMPORTANT: Edit .env.production with your backend URL!${NC}"
    read -p "Press Enter to continue or Ctrl+C to cancel..."
fi

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
npm install

# Build frontend
echo -e "${YELLOW}Building frontend...${NC}"
npm run build

# Check if build was successful
if [ ! -d "dist" ]; then
    echo -e "${RED}Error: Build failed - dist directory not found${NC}"
    exit 1
fi

echo -e "${GREEN}Build successful!${NC}"
echo ""

# Deploy to Firebase
echo -e "${YELLOW}Deploying to Firebase Hosting...${NC}"
cd ..
firebase deploy --only hosting

# Get hosting URL
HOSTING_URL="https://${PROJECT_ID}.web.app"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Successful!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Frontend URL: ${GREEN}${HOSTING_URL}${NC}"
echo -e "Alternative:  ${GREEN}https://${PROJECT_ID}.firebaseapp.com${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Update backend CORS_ORIGINS to include:"
echo "   ${HOSTING_URL}"
echo ""
echo "2. Test the frontend:"
echo "   Open ${HOSTING_URL} in your browser"
echo ""
echo -e "${YELLOW}View deployment:${NC}"
echo "   firebase hosting:channel:list"
echo ""
echo -e "${YELLOW}Rollback if needed:${NC}"
echo "   firebase hosting:clone ${PROJECT_ID}:SOURCE_CHANNEL ${PROJECT_ID}:live"
echo ""
