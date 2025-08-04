# Cloudflare Tunnel Setup for aeroguessr.com

This guide explains how to expose your Raspberry Pi-hosted Plane Game to the internet using Cloudflare Tunnel at aeroguessr.com.

## Overview

Cloudflare Tunnel creates a secure connection between your Raspberry Pi and Cloudflare's edge network without requiring port forwarding or a static IP address. This provides:

- **Automatic HTTPS** - SSL certificates managed by Cloudflare
- **DDoS Protection** - Built-in protection from attacks
- **No Port Forwarding** - Works behind NAT/firewalls
- **Automatic Reconnection** - Resilient to network changes

## Prerequisites

1. **Domain Ownership** - You must own aeroguessr.com and have it added to your Cloudflare account
2. **Cloudflare Account** - Free tier is sufficient
3. **Running Game** - Docker containers must be running on the Pi (port 80)
4. **SSH Access** - Ability to SSH into your Raspberry Pi

## Quick Setup

We've created an automated setup script that handles the entire installation process:

```bash
# SSH into your Pi
ssh pi@192.168.1.181

# Navigate to project directory
cd /home/pi/plane-game-v4

# Run the setup script
bash scripts/setup-cloudflare-tunnel.sh
```

The script will:
1. Install cloudflared (if not already installed)
2. Authenticate with your Cloudflare account (opens browser)
3. Create a tunnel named "aeroguessr"
4. Configure DNS routing for aeroguessr.com and www.aeroguessr.com
5. Create the tunnel configuration
6. Set up systemd service for auto-start
7. Start the tunnel

## Manual Setup Steps

If you prefer manual setup or need to troubleshoot:

### 1. Install cloudflared

```bash
# Download ARM64 version for Raspberry Pi
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb
rm cloudflared-linux-arm64.deb
```

### 2. Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

This opens a browser window. If running via SSH, copy the URL and open it on your local machine.

### 3. Create the Tunnel

```bash
cloudflared tunnel create aeroguessr
```

### 4. Configure DNS

```bash
# Route the domain to your tunnel
cloudflared tunnel route dns aeroguessr aeroguessr.com
cloudflared tunnel route dns aeroguessr www.aeroguessr.com
```

### 5. Create Configuration File

Create `/home/pi/.cloudflared/config.yml`:

```yaml
tunnel: YOUR_TUNNEL_ID
credentials-file: /home/pi/.cloudflared/YOUR_TUNNEL_ID.json

ingress:
  - service: http://localhost:80
    originRequest:
      noTLSVerify: true
      keepAliveConnections: 10
      connectTimeout: 30s
```

### 6. Create Systemd Service

Copy the service file:
```bash
sudo cp /home/pi/plane-game-v4/infra/cloudflared.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

## Configuration Details

### Tunnel Configuration (`infra/cloudflared-config.yml`)

The configuration file defines how traffic is routed:

- **Health checks** - Special handling for `/healthz` endpoint
- **API routes** - `/api/*` traffic with appropriate timeouts
- **WebSocket routes** - `/ws/*` with WebSocket-specific settings
- **Frontend** - All other traffic serves the React app

### Frontend Environment (`frontend/.env.production`)

Production build uses these environment variables:

```env
VITE_API_BASE_URL=https://aeroguessr.com/api/v0
VITE_WS_BASE_URL=wss://aeroguessr.com
```

These are automatically used when building for production.

## Testing the Setup

### 1. Check Tunnel Status

```bash
sudo systemctl status cloudflared
```

### 2. View Tunnel Logs

```bash
sudo journalctl -u cloudflared -f
```

### 3. Test Public Access

Open in your browser:
- https://aeroguessr.com
- https://www.aeroguessr.com

### 4. Test WebSocket Connection

The game should connect automatically. Check browser console for WebSocket connection status.

## Troubleshooting

### Tunnel Won't Start

1. Check logs: `sudo journalctl -u cloudflared -n 50`
2. Verify Docker is running: `docker compose ps`
3. Test local access: `curl http://localhost/healthz`

### DNS Not Resolving

1. Check Cloudflare dashboard for DNS records
2. Wait 5-10 minutes for DNS propagation
3. Try: `nslookup aeroguessr.com`

### WebSocket Connection Failed

1. Check nginx configuration includes WebSocket headers
2. Verify `/ws/` location block in nginx.conf
3. Check browser console for specific errors

### Certificate Errors

1. Cloudflare handles SSL automatically
2. Ensure Cloudflare SSL mode is "Full" or "Flexible"
3. Check tunnel logs for certificate issues

## Maintenance

### Restart Tunnel

```bash
sudo systemctl restart cloudflared
```

### Update cloudflared

```bash
# Download latest version
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb
sudo systemctl restart cloudflared
```

### View Tunnel List

```bash
cloudflared tunnel list
```

### Delete Tunnel (if needed)

```bash
cloudflared tunnel delete aeroguessr
```

## Security Considerations

1. **Access Control** - The tunnel exposes your application to the internet
2. **Rate Limiting** - Nginx configuration includes rate limiting
3. **Monitoring** - Check logs regularly for suspicious activity
4. **Updates** - Keep cloudflared and Docker images updated

## Integration with Deployment

The `deploy-to-pi.sh` script now checks for Cloudflare tunnel status and provides setup instructions if not configured.

## Next Steps

1. Set up Cloudflare Access for authentication (optional)
2. Configure Cloudflare Analytics for traffic insights
3. Set up alerts for tunnel downtime
4. Consider Cloudflare Workers for additional functionality

## Resources

- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Cloudflare Dashboard](https://dash.cloudflare.com/)
- [Project README](../README.md)
- [Raspberry Pi Deployment Guide](../infra/README.md)
