# Infrastructure & Deployment Guide

Docker-based deployment targeting Raspberry Pi with live ADS-B data.

## Target Environment

- **Platform**: Raspberry Pi 4 Model B (ARM64)
- **IP**: 192.168.1.181
- **SSH**: `ssh pi-plane` (alias in ~/.ssh/config)
- **OS**: Debian GNU/Linux (64-bit)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Raspberry Pi                             │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Nginx     │  │   Backend   │  │   Redis     │         │
│  │   (80)      │  │   (8000)    │  │   (6379)    │         │
│  │   Frontend  │  │   API+Ingest│  │   State     │         │
│  └──────┬──────┘  └──────┬──────┘  └─────────────┘         │
│         │                │                                  │
│         │         ┌──────┴──────┐                          │
│         │         │  dump1090   │                          │
│         │         │  (30003)    │                          │
│         │         │  ADS-B Data │                          │
│         │         └─────────────┘                          │
└─────────┴───────────────────────────────────────────────────┘
```

## Docker Stack

### Files
| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base configuration |
| `docker-compose.pi.yml` | Pi-specific overrides |
| `Dockerfile.backend` | Backend image (API + Ingest) |
| `Dockerfile.frontend` | Frontend static build |

### Services
```yaml
services:
  backend:
    # FastAPI + Ingest via supervisord
    ports: ["8000:8000"]

  frontend:
    # Nginx serving static React build
    ports: ["80:80"]

  redis:
    ports: ["6379:6379"]
```

## Deployment Process

### From Development Machine

```bash
# 1. Sync code to Pi (code is baked into image, not mounted)
rsync -avz --exclude node_modules --exclude .git \
  . pi@192.168.1.181:/home/pi/plane-game-v4/

# 2. SSH to Pi
ssh pi-plane
```

### On Raspberry Pi

```bash
cd /home/pi/plane-game-v4/infra

# 3. Rebuild containers
docker compose -f docker-compose.yml build --no-cache

# 4. Restart services
docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d

# 5. Verify
docker compose ps
docker compose logs backend --tail 50
```

## ADS-B Setup

### dump1090-mutability
```bash
# Status
sudo systemctl status dump1090-mutability

# Restart
sudo systemctl restart dump1090-mutability

# Test data stream
timeout 5 bash -c 'exec 3<>/dev/tcp/localhost/30003; head -3 <&3'

# Web interface
http://192.168.1.181:8080
```

### Configuration
```bash
# /etc/default/dump1090-mutability
START_DUMP1090="yes"
GAIN="max"                    # 49.60 dB
SBS_OUTPUT_PORT="30003"       # App connects here
NET_HTTP_PORT=8080            # Web interface
JSON_DIR="/run/dump1090-mutability"
JSON_INTERVAL="1"
```

## Environment Configuration

### Pi .env File
```bash
# /home/pi/plane-game-v4/.env
FAKE_ADSB=0                    # Live data (not synthetic)
ADSB_HOST=host.docker.internal # Connect to host's dump1090
ADSB_PORT=30003
CENTER_LAT=42.3656             # Boston Logan
CENTER_LON=-71.0096
REDIS_URL=redis://redis:6379/0
ENRICHMENT_V2_ENABLED=true
```

## Troubleshooting

### Container Issues
```bash
# Full restart
docker compose down
docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d

# Rebuild specific service
docker compose build backend --no-cache
docker compose up -d backend

# View logs
docker compose logs backend -f
docker compose logs frontend -f
```

### ADS-B Connection Issues
```bash
# Check dump1090 is running
sudo systemctl status dump1090-mutability

# Verify port 30003
netstat -ln | grep 30003

# Test from container
docker compose exec backend nc -zv host.docker.internal 30003
```

### Network Issues
```bash
# Check ports
netstat -ln | grep -E ':(80|8000|6379)'

# Check Pi IP
ip addr show wlan0
```

## Monitoring

```bash
# Container resources
docker stats

# System resources
htop
free -h
df -h

# Backend logs
docker compose logs backend --tail 100 | grep -i error
```

## Quick Reference

| Action | Command |
|--------|---------|
| SSH to Pi | `ssh pi-plane` |
| Rebuild & restart | `docker compose build --no-cache && docker compose up -d` |
| View logs | `docker compose logs -f` |
| Stop all | `docker compose down` |
| Check ADS-B | `sudo systemctl status dump1090-mutability` |
| Test API | `curl http://localhost:8000/healthz` |
