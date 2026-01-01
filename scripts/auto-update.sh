#!/bin/bash
# Auto-update script - polls GitHub and rebuilds on changes
# Deployed to Pi at /home/pi/plane-game-v4/scripts/auto-update.sh
# Run by systemd timer every 1 minute

set -e

cd /home/pi/plane-game-v4

# Fetch latest from origin
git fetch origin main

# Check if we're behind
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "$(date): Already up to date"
    exit 0
fi

echo "$(date): New commits detected, updating..."

# Pull changes
git pull origin main

# Rebuild and restart
docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml build
docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml up -d

# Health check
sleep 10
if curl -sf http://localhost/healthz > /dev/null; then
    echo "$(date): Deploy successful!"
else
    echo "$(date): Health check failed!"
    exit 1
fi
