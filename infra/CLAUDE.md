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

## CI/CD Pipeline

Automated deployment pipeline via GitHub Actions with Cloudflare Tunnel for secure SSH access.

### Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         GitHub Actions                                │
├──────────────────────────────────────────────────────────────────────┤
│  1. Test (pytest)                                                     │
│  2. Build ARM64 images (QEMU/Buildx)                                 │
│  3. Push to GHCR (ghcr.io/tcole333/plane-game-v4)                   │
│  4. SSH via Cloudflare Tunnel → Pi                                   │
│  5. Run deployment script                                            │
│  6. Health check + auto-rollback on failure                          │
└──────────────────────────────────────────────────────────────────────┘
          │
          │ cloudflared access ssh
          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     Cloudflare Tunnel                                 │
│                     ssh.aeroguessr.com                               │
└──────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       Raspberry Pi                                    │
│  - Pull images from GHCR                                             │
│  - docker compose up with new images                                 │
│  - Health check validation                                           │
└──────────────────────────────────────────────────────────────────────┘
```

### Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `deploy.yml` | Push to main | Build, push, and deploy to Pi |
| `rollback.yml` | Manual dispatch | Rollback to a specific version |

### Files

| File | Location | Purpose |
|------|----------|---------|
| `docker-compose.deploy.yml` | `infra/` | Production compose using GHCR images |
| `ci-deploy.sh` | `scripts/` | Pi-side deployment script |

### GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `PI_SSH_PRIVATE_KEY` | Ed25519 SSH key for Pi access |
| `FLIGHTAWARE_API_KEY` | FlightAware API key for enrichment |
| `OPENSKY_USERNAME` | OpenSky API username |
| `OPENSKY_PASSWORD` | OpenSky API password |

### Deployment Process

1. **Automatic (on push to main)**:
   ```
   Tests pass → Build ARM64 images → Push to GHCR → Deploy to Pi → Health check
   ```

2. **Manual Rollback**:
   - Go to Actions → Rollback Deployment
   - Enter the commit SHA or tag to rollback to
   - Workflow validates image exists, then deploys

### Version Tracking

On the Pi, version tracking files are maintained in `/home/pi/plane-game-v4/infra/`:

| File | Purpose |
|------|---------|
| `.current_tag` | Currently deployed version |
| `.previous_tag` | Previous version (for rollback) |

### Manual Deployment Commands

```bash
# SSH to Pi via Cloudflare Tunnel (from dev machine)
cloudflared access ssh --hostname ssh.aeroguessr.com

# Or if SSH config is set up:
ssh pi-deploy

# Check current version
cat /home/pi/plane-game-v4/infra/.current_tag

# Manual deployment with specific tag
cd /home/pi/plane-game-v4/infra
IMAGE_TAG=abc123def docker compose -f docker-compose.deploy.yml -f docker-compose.pi.yml up -d

# View deployment logs
docker compose logs -f
```

### Rollback Procedure

**Automatic rollback** happens when health check fails after deployment.

**Manual rollback** via GitHub Actions:
1. Go to Actions → "Rollback Deployment"
2. Click "Run workflow"
3. Enter the version/SHA to rollback to
4. Add reason (optional)
5. Run

**Emergency manual rollback** on Pi:
```bash
cd /home/pi/plane-game-v4/infra
PREVIOUS_TAG=$(cat .previous_tag)
IMAGE_TAG=$PREVIOUS_TAG docker compose -f docker-compose.deploy.yml -f docker-compose.pi.yml up -d
```

### Troubleshooting CI/CD

```bash
# Check GitHub Actions logs
# Go to: https://github.com/tcole333/plane-game-v4/actions

# On Pi: Check if images were pulled
docker images | grep ghcr.io

# Check container status
docker compose ps

# Check deployment script logs
journalctl -f  # System logs

# Verify Cloudflare Tunnel is running
sudo systemctl status cloudflared
```
