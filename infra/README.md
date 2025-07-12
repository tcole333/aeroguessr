# Raspberry Pi Deployment Guide

This document provides comprehensive information about deploying the Plane Guessing Game on a Raspberry Pi with live ADS-B data.

## Current Pi Configuration Status

### Hardware Configuration
- **Model**: Raspberry Pi 4 Model B Rev 1.5
- **CPU**: 4-core ARM64 (aarch64)
- **Memory**: 3.7GB RAM
- **Storage**: 117GB SD card (7% used, 104GB available)
- **OS**: Debian GNU/Linux (Kernel 6.6.74+rpt-rpi-v8)
- **Network**: WiFi connected at 192.168.1.181

### ADS-B Setup Status ✅

#### Hardware
- **RTL-SDR Device**: Realtek RTL2838 DVB-T (Bus 001 Device 003: ID 0bda:2838)
- **Status**: Connected and functioning
- **Gain**: 49.60 dB (maximum)
- **Location**: Boston area (around 42.38°N, 71.01°W)

#### Software
- **Installed**: dump1090-mutability v1.15~20180310 (Debian package)
- **Status**: Running and receiving live flight data
- **Auto-start**: Enabled (starts on boot)

#### Services
```bash
# Main ADS-B receiver service
sudo systemctl status dump1090-mutability    # ✅ Active (running)
sudo systemctl status dump1090-http          # ✅ Active (running)

# Service ports
Port 30003: SBS-1 format data stream          # ✅ Active
Port 8080:  HTTP web interface               # ✅ Active
```

#### Live Data Verification
- **Flight Data**: ✅ Receiving real flights (JetBlue, Delta, Republic Airways, etc.)
- **SBS Stream**: ✅ Port 30003 outputting SBS-1 format messages
- **JSON Files**: ✅ Updated every 1 second in `/run/dump1090-mutability/`
- **Location Data**: ✅ Aircraft positions around Boston Logan area

### Current Configuration Files

#### /etc/default/dump1090-mutability
```bash
START_DUMP1090="yes"
DEVICE=""                    # Auto-detect RTL-SDR
GAIN="max"                  # Maximum gain (49.60 dB)
SBS_OUTPUT_PORT="30003"     # Our app connects here
NET_HTTP_PORT=8080          # Web interface
JSON_DIR="/run/dump1090-mutability"
JSON_INTERVAL="1"           # Update every second
MAX_RANGE="300"             # 300 nautical miles
```

## Docker Deployment Plan

### Prerequisites
The following issues must be completed before Pi deployment:

- [ ] Issue #89: Fix Backend Dockerfile app path and networking
- [ ] Issue #90: Create Frontend Dockerfile for production build
- [ ] Issue #91: Create complete docker-compose.yml with networking
- [ ] Issue #92: Create Nginx configuration for reverse proxy

### Docker Installation (Required)
```bash
# Install Docker on the Pi
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker pi

# Install Docker Compose
sudo apt update
sudo apt install docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### Deployment Process

#### 1. Environment Configuration
```bash
# On the Pi, create .env file
cd /home/pi/plane-game-v4
cp .env.example .env

# Critical settings for live ADS-B:
FAKE_ADSB=0                    # Use live data, not synthetic
ADSB_HOST=127.0.0.1            # Connect to local dump1090
ADSB_PORT=30003                # SBS-1 format port
CENTER_LAT=42.3656             # Boston Logan coordinates
CENTER_LON=-71.0096
```

#### 2. Docker Deployment
```bash
# Deploy complete stack
docker compose -f infra/docker-compose.yml up -d

# Verify services
docker compose ps
docker compose logs backend | tail -20
docker compose logs frontend | tail -10
```

#### 3. Network Access Testing
```bash
# Test from Pi
curl http://localhost/api/v0/healthz

# Test from another device on network
curl http://192.168.1.181/api/v0/healthz

# Test WebSocket (should show flight data)
# Open browser to: http://192.168.1.181
```

## Troubleshooting

### ADS-B Issues

#### Check ADS-B Service Status
```bash
# Service status
sudo systemctl status dump1090-mutability
sudo systemctl status dump1090-http

# Check for RTL-SDR device
lsusb | grep -i rtl

# Test data stream
timeout 5 bash -c 'exec 3<>/dev/tcp/localhost/30003; head -3 <&3'

# Check JSON output
ls -la /run/dump1090-mutability/
head /run/dump1090-mutability/aircraft.json
```

#### Restart ADS-B Services
```bash
sudo systemctl restart dump1090-mutability
sudo systemctl restart dump1090-http
```

### Docker Issues

#### Container Logs
```bash
docker compose logs backend
docker compose logs frontend
docker compose logs nginx
```

#### Network Connectivity
```bash
# Check if ports are open
netstat -ln | grep -E ':(80|8000|6379)'

# Check Pi network interfaces
ip addr show
```

### Application Issues

#### Backend Connection to ADS-B
```bash
# Check backend logs for ADS-B connection
docker compose logs backend | grep -i "adsb\|connection\|ingest"

# Verify environment variables
docker compose exec backend env | grep ADSB
```

## Performance Monitoring

### System Resources
```bash
# Monitor system load
htop

# Check disk space
df -h

# Check memory usage
free -h

# Monitor container resources
docker stats
```

### ADS-B Performance
```bash
# Check message count and aircraft count
curl -s http://localhost:8080/stats.json | python3 -m json.tool

# Monitor antenna performance
tail -f /var/log/dump1090-mutability.log
```

## External Access Options

### Option 1: Cloudflare Tunnel (Recommended)
```bash
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb

# Setup tunnel (requires Cloudflare account)
cloudflared tunnel login
cloudflared tunnel create plane-game
cloudflared tunnel route dns plane-game your-domain.com
cloudflared tunnel run plane-game --url http://localhost:80
```

### Option 2: Router Port Forwarding
1. Configure router to forward port 80 to 192.168.1.181:80
2. Set up dynamic DNS service (DuckDNS, No-IP, etc.)
3. Access via your-domain.duckdns.org

### Option 3: Tailscale VPN
```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

## Maintenance

### Automatic Updates
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Docker images
docker compose pull
docker compose up -d
```

### Log Management
```bash
# Check log sizes
du -sh /var/log/dump1090-mutability.log
docker system df

# Clean up old containers/images
docker system prune -f
```

### Backup Configuration
```bash
# Backup critical files
tar -czf pi-config-backup.tar.gz \
  /etc/default/dump1090-mutability \
  /etc/systemd/system/dump1090-http.service \
  /home/pi/plane-game-v4/.env
```

## Security Considerations

### Basic Security
- Change default Pi password: `passwd`
- Enable SSH key authentication
- Configure firewall: `sudo ufw enable`
- Regular security updates: `sudo apt update && sudo apt upgrade`

### Network Security
- Use strong WiFi passwords
- Consider VPN access instead of port forwarding
- Monitor access logs: `docker compose logs nginx | grep -E '(GET|POST)'`

---

## Quick Start Checklist

- [ ] Pi is accessible via SSH (pi@192.168.1.181)
- [ ] RTL-SDR device is connected and detected
- [ ] dump1090-mutability service is running
- [ ] Port 30003 is providing SBS-1 data
- [ ] Docker is installed
- [ ] Issues #89-#92 are completed
- [ ] .env file is configured for live data (FAKE_ADSB=0)
- [ ] docker-compose.yml deployment works
- [ ] Game is accessible from network devices
- [ ] Real flight data appears in the game

**Pi IP Address**: 192.168.1.181
**Game URL**: http://192.168.1.181 (after Docker deployment)
**ADS-B Interface**: http://192.168.1.181:8080 (currently working)
