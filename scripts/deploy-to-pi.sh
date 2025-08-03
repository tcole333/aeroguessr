#!/bin/bash
# Deploy Plane Game v4 to Raspberry Pi for testing with live ADS-B data

set -e

# Configuration
PI_USER="pi"
PI_HOST="192.168.1.181"
PROJECT_DIR="/home/pi/plane-game-v4"

echo "🚀 Deploying Plane Game v4 to Raspberry Pi..."

# Function to run commands on Pi
run_on_pi() {
    ssh "${PI_USER}@${PI_HOST}" "$1"
}

# 1. Ensure project directory exists
echo "📁 Setting up project directory..."
run_on_pi "mkdir -p ${PROJECT_DIR}"

# 2. Sync code to Pi (excluding unnecessary files)
echo "📤 Syncing code to Pi..."
rsync -av --exclude='.git' \
          --exclude='node_modules' \
          --exclude='__pycache__' \
          --exclude='.pytest_cache' \
          --exclude='logs/*' \
          --exclude='.env' \
          ./ "${PI_USER}@${PI_HOST}:${PROJECT_DIR}/"

# 3. Create .env file on Pi if it doesn't exist
echo "🔧 Setting up environment..."
run_on_pi "cd ${PROJECT_DIR} && [ -f .env ] || cp .env.example .env"

# 4. Update .env for live ADS-B data
echo "📡 Configuring for live ADS-B data..."
run_on_pi "cd ${PROJECT_DIR} && sed -i 's/FAKE_ADSB=.*/FAKE_ADSB=0/' .env"
run_on_pi "cd ${PROJECT_DIR} && sed -i 's/ADSB_HOST=.*/ADSB_HOST=127.0.0.1/' .env"
run_on_pi "cd ${PROJECT_DIR} && sed -i 's/ENRICHMENT_V2_ENABLED=.*/ENRICHMENT_V2_ENABLED=1/' .env"

# Update Kalman filter parameters for better plane tracking
echo "🎯 Updating Kalman filter parameters..."
run_on_pi "cd ${PROJECT_DIR} && sed -i 's/KALMAN_PROCESS_NOISE=.*/KALMAN_PROCESS_NOISE=0.01/' .env"
run_on_pi "cd ${PROJECT_DIR} && sed -i 's/KALMAN_MEASUREMENT_NOISE=.*/KALMAN_MEASUREMENT_NOISE=3.0/' .env"

# 5. Ensure FlightAware API key is set
echo "🔑 Checking API keys..."
run_on_pi "cd ${PROJECT_DIR} && grep -q 'FLIGHTAWARE_API_KEY=' .env || echo 'FLIGHTAWARE_API_KEY=' >> .env"
echo "⚠️  Please ensure FLIGHTAWARE_API_KEY is set in ${PROJECT_DIR}/.env on the Pi!"

# 6. Build and start Docker containers
echo "🐳 Building and starting Docker containers..."
run_on_pi "cd ${PROJECT_DIR} && docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml build"
run_on_pi "cd ${PROJECT_DIR} && docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml up -d"

# 7. Wait for services to be healthy
echo "⏳ Waiting for services to start..."
sleep 10

# 8. Check service status
echo "✅ Checking service status..."
run_on_pi "cd ${PROJECT_DIR} && docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml ps"

# 9. Show logs
echo "📋 Recent backend logs:"
run_on_pi "cd ${PROJECT_DIR} && docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml logs backend --tail=20"

# 10. Test endpoints
echo "🧪 Testing endpoints..."
echo "Health check:"
curl -s "http://${PI_HOST}/api/v0/healthz" | jq .

echo ""
echo "✨ Deployment complete!"
echo "📱 Access the game at: http://${PI_HOST}"
echo "📊 Monitor enrichment stats in backend logs:"
echo "   ssh ${PI_USER}@${PI_HOST} 'cd ${PROJECT_DIR} && docker compose logs -f backend | grep -i enrichment'"
echo ""
echo "🔍 To check if flights are being enriched:"
echo "   ssh ${PI_USER}@${PI_HOST} 'cd ${PROJECT_DIR} && docker compose exec redis redis-cli KEYS \"aeroapi_route_v2:*\" | head -10'"
