#!/bin/bash
# Monitor flight enrichment performance on Raspberry Pi

set -e

# Configuration
PI_USER="pi"
PI_HOST="192.168.1.181"
PROJECT_DIR="/home/pi/plane-game-v4"

echo "📊 Monitoring Flight Enrichment on Raspberry Pi..."
echo "Press Ctrl+C to stop"
echo ""

# SSH into Pi and run monitoring commands
ssh "${PI_USER}@${PI_HOST}" << 'EOF'
cd /home/pi/plane-game-v4

echo "🔍 Checking enrichment statistics..."
echo ""

# Function to get enrichment stats from logs
monitor_enrichment() {
    while true; do
        clear
        echo "=== FLIGHT ENRICHMENT MONITOR ==="
        echo "Time: $(date)"
        echo ""

        # Check Redis for cached enrichment data
        echo "📦 Cached enrichment entries (V2):"
        docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml exec -T redis redis-cli KEYS "aeroapi_route_v2:*" | wc -l

        echo ""
        echo "📦 Cached scheduled flights:"
        docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml exec -T redis redis-cli EXISTS "flight_schedule:KBOS" && echo "✅ Schedule cache exists" || echo "❌ No schedule cache"

        echo ""
        echo "✈️  Active planes:"
        docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml exec -T redis redis-cli KEYS "plane:*" | wc -l

        echo ""
        echo "📊 Recent enrichment stats (last 5 minutes):"
        docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml logs backend --since=5m 2>/dev/null | grep -i "enrichment statistics" | tail -5

        echo ""
        echo "🎯 Recent matches:"
        docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml logs backend --since=5m 2>/dev/null | grep -E "(Found flight|Match found)" | tail -10

        echo ""
        echo "❌ Recent failures:"
        docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml logs backend --since=5m 2>/dev/null | grep -E "(No match found|enrichment.*failed)" | tail -5

        echo ""
        echo "🔄 Refreshing in 30 seconds..."
        sleep 30
    done
}

# Run the monitoring function
monitor_enrichment
EOF
