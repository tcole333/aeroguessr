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

### Pull-Based Auto-Deployment

The Pi automatically polls GitHub every 1 minute and deploys new changes. No GitHub Actions or container registry needed - builds happen natively on the Pi for faster ARM64 compilation (~3-5 min vs 30+ min with QEMU emulation).

**How it works:**
1. Push changes to `main` branch
2. Within 1 minute, Pi detects new commits via `git fetch`
3. Pi pulls changes, rebuilds Docker images natively, and restarts services
4. Health check validates deployment

**Monitoring auto-updates:**
```bash
ssh pi-plane

# Check timer status
systemctl status plane-game-update.timer
systemctl list-timers | grep plane

# View update logs
tail -f /home/pi/plane-game-v4/logs/auto-update.log

# Trigger manual update
/home/pi/plane-game-v4/scripts/auto-update.sh
```

**Auto-update components:**
| File | Location | Purpose |
|------|----------|---------|
| `auto-update.sh` | `scripts/` | Polls GitHub, rebuilds on changes |
| `plane-game-update.service` | `/etc/systemd/system/` | Systemd service unit |
| `plane-game-update.timer` | `/etc/systemd/system/` | 1-minute timer |
| `auto-update.log` | `logs/` | Deployment history |

### Manual Deployment (Fallback)

```bash
# SSH to Pi
ssh pi-plane
cd /home/pi/plane-game-v4

# Pull latest changes
git pull origin main

# Rebuild containers
docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml build

# Restart services
docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml up -d

# Verify
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

## Deployment Architecture

### Pull-Based Auto-Deployment

The Pi uses a simple pull-based deployment model - it polls GitHub every 1 minute and auto-deploys on changes. This approach was chosen over GitHub Actions + GHCR because:

1. **Faster builds**: Native ARM64 builds take ~3-5 min vs 30+ min with QEMU emulation
2. **Simpler infrastructure**: No container registry, no GitHub secrets management
3. **Lower latency**: 1-minute polling vs waiting for CI/CD pipeline completion
4. **Offline resilience**: Pi can continue running even if GitHub Actions is down

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Developer Workstation                           │
├──────────────────────────────────────────────────────────────────────┤
│  1. Make changes locally                                              │
│  2. Push to main branch                                               │
└──────────────────────────────────────────────────────────────────────┘
          │
          │ git push
          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          GitHub                                       │
│                    (main branch)                                      │
└──────────────────────────────────────────────────────────────────────┘
          │
          │ git fetch (every 1 min)
          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       Raspberry Pi                                    │
│  - systemd timer runs auto-update.sh every 1 min                     │
│  - Detects new commits, pulls changes                                │
│  - Rebuilds Docker images natively (fast ARM64)                      │
│  - Restarts containers                                               │
│  - Health check validates deployment                                 │
└──────────────────────────────────────────────────────────────────────┘
```

### Pi Auto-Update Components

| Component | Path | Purpose |
|-----------|------|---------|
| Timer | `/etc/systemd/system/plane-game-update.timer` | Triggers every 1 minute |
| Service | `/etc/systemd/system/plane-game-update.service` | Runs the update script |
| Script | `/home/pi/plane-game-v4/scripts/auto-update.sh` | Git pull + Docker rebuild |
| Logs | `/home/pi/plane-game-v4/logs/auto-update.log` | Deployment history |

### Monitoring Deployments

```bash
ssh pi-plane

# Check timer status
systemctl status plane-game-update.timer
systemctl list-timers | grep plane

# View recent deployments
tail -50 /home/pi/plane-game-v4/logs/auto-update.log

# Watch live updates
tail -f /home/pi/plane-game-v4/logs/auto-update.log

# Trigger immediate update
/home/pi/plane-game-v4/scripts/auto-update.sh
```

### Version Tracking

```bash
# Check current commit on Pi
ssh pi-plane "cd /home/pi/plane-game-v4 && git log -1 --oneline"

# Compare with remote
ssh pi-plane "cd /home/pi/plane-game-v4 && git fetch && git log HEAD..origin/main --oneline"
```

### Rollback Procedure

```bash
ssh pi-plane
cd /home/pi/plane-game-v4

# View recent commits
git log --oneline -10

# Rollback to specific commit
git reset --hard <commit-sha>
docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml build
docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml up -d
```

### Troubleshooting

```bash
# Check timer is active
systemctl status plane-game-update.timer

# Check last update run
journalctl -u plane-game-update.service -n 50

# Manual test of update script
/home/pi/plane-game-v4/scripts/auto-update.sh

# Check for git issues
cd /home/pi/plane-game-v4 && git status
```

### GitHub Deploy Key

The Pi uses a deploy key for read-only GitHub access:
- Key location: `/home/pi/.ssh/id_ed25519`
- Added via `gh repo deploy-key add` with title "pi-plane-deploy"
- Read-only access to pull changes
