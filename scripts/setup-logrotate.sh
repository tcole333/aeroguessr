#!/bin/bash
# Setup script for log rotation on deployment server

echo "Setting up log rotation for AeroGuessr..."

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo: sudo ./setup-logrotate.sh"
    exit 1
fi

# Copy logrotate configuration
if [ -f "/etc/logrotate.d/plane-game" ]; then
    echo "Backing up existing logrotate config..."
    cp /etc/logrotate.d/plane-game /etc/logrotate.d/plane-game.bak
fi

echo "Installing logrotate configuration..."
cp infra/logrotate.d/plane-game /etc/logrotate.d/plane-game

# Update the path in the config to match actual deployment location
DEPLOY_PATH=$(pwd)
sed -i "s|/home/pi/plane-game-v4|${DEPLOY_PATH}|g" /etc/logrotate.d/plane-game

# Set correct permissions
chmod 644 /etc/logrotate.d/plane-game

# Test the configuration
echo "Testing logrotate configuration..."
logrotate -d /etc/logrotate.d/plane-game

echo "Log rotation setup complete!"
echo "Logs will be rotated according to the following schedule:"
echo "- Daily rotation"
echo "- Keep only 1 day of history (yesterday's log)"
echo "- Compress old logs"
echo "- Rotate when size exceeds 5MB"
