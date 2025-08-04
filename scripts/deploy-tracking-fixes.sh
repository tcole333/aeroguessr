#!/bin/bash
# Deploy plane tracking fixes to Raspberry Pi

set -e

echo "🚀 Deploying plane tracking fixes to Raspberry Pi..."

# Configuration
PI_HOST="pi@raspberrypi.local"
PROJECT_DIR="/home/pi/plane-game-v4"

# Function to run commands on Pi
run_on_pi() {
    ssh $PI_HOST "$1"
}

# 1. Copy updated backend files
echo "📦 Copying backend fixes..."
scp backend/ingest/parser.py $PI_HOST:$PROJECT_DIR/backend/ingest/
scp backend/ingest/main.py $PI_HOST:$PROJECT_DIR/backend/ingest/

# 2. Copy updated frontend file
echo "📦 Copying frontend fix..."
scp frontend/src/features/planes/components/PlaneDetails.tsx $PI_HOST:$PROJECT_DIR/frontend/src/features/planes/components/

# 3. Copy investigation documentation and scripts
echo "📋 Copying investigation files..."
scp docs/plane-tracking-investigation.md $PI_HOST:$PROJECT_DIR/docs/
scp scripts/analyze-adsb-raw.py $PI_HOST:$PROJECT_DIR/scripts/
chmod +x scripts/analyze-adsb-raw.py
scp scripts/test-sbs-coordinate-bug.py $PI_HOST:$PROJECT_DIR/scripts/

# 4. Rebuild and restart backend container
echo "🐳 Rebuilding backend container..."
run_on_pi "cd $PROJECT_DIR && docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml build backend"

echo "♻️  Restarting backend..."
run_on_pi "cd $PROJECT_DIR && docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml restart backend"

# 5. Check logs for startup
echo "📊 Checking backend logs..."
sleep 5
run_on_pi "cd $PROJECT_DIR && docker logs plane-game-v4-backend-1 --tail 50"

echo "✅ Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Monitor the logs: ssh $PI_HOST 'cd $PROJECT_DIR && docker logs -f plane-game-v4-backend-1'"
echo "2. Check the map UI for smooth plane movement"
echo "3. Look for MSG,2 messages in the logs to verify fix"
echo ""
echo "To run raw ADS-B analysis on Pi:"
echo "ssh $PI_HOST 'cd $PROJECT_DIR && python scripts/analyze-adsb-raw.py'"
