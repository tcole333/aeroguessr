#!/bin/bash
set -e

# Wait for Redis to be ready (if needed)
echo "Starting backend services..."

# Start supervisord
exec supervisord -c /app/supervisord.conf
