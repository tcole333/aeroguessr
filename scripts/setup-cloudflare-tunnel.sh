#!/bin/bash
# Setup Cloudflare Tunnel for aeroguessr.com on Raspberry Pi
# This script installs cloudflared and configures it to expose the game

set -e

# Configuration
TUNNEL_NAME="aeroguessr"
DOMAIN="aeroguessr.com"
LOCAL_URL="http://localhost:80"
CONFIG_DIR="/home/pi/.cloudflared"
SERVICE_NAME="cloudflared"

echo "🚀 Setting up Cloudflare Tunnel for ${DOMAIN}..."

# Function to check if running on Pi
check_pi() {
    if [[ ! -f /proc/cpuinfo ]] || ! grep -q "Raspberry Pi" /proc/cpuinfo; then
        echo "⚠️  Warning: This script is designed for Raspberry Pi"
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Function to install cloudflared
install_cloudflared() {
    echo "📦 Installing cloudflared..."

    # Check if already installed
    if command -v cloudflared &> /dev/null; then
        echo "✅ cloudflared is already installed"
        cloudflared --version
        return
    fi

    # Download and install ARM64 version
    wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
    sudo dpkg -i cloudflared-linux-arm64.deb
    rm cloudflared-linux-arm64.deb

    echo "✅ cloudflared installed successfully"
    cloudflared --version
}

# Function to authenticate with Cloudflare
authenticate_cloudflare() {
    echo "🔐 Authenticating with Cloudflare..."
    echo "This will open a browser window for authentication"
    echo "If running via SSH, you may need to copy the URL and open it on your local machine"

    cloudflared tunnel login

    echo "✅ Authentication complete"
}

# Function to create tunnel
create_tunnel() {
    echo "🚇 Creating tunnel '${TUNNEL_NAME}'..."

    # Check if tunnel already exists
    if cloudflared tunnel list | grep -q "${TUNNEL_NAME}"; then
        echo "⚠️  Tunnel '${TUNNEL_NAME}' already exists"
        read -p "Delete and recreate? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Deleting existing tunnel..."
            cloudflared tunnel delete "${TUNNEL_NAME}"
        else
            echo "Using existing tunnel"
            return
        fi
    fi

    # Create new tunnel
    cloudflared tunnel create "${TUNNEL_NAME}"

    echo "✅ Tunnel created successfully"
}

# Function to configure DNS
configure_dns() {
    echo "🌐 Configuring DNS for ${DOMAIN}..."

    # Route root domain
    cloudflared tunnel route dns "${TUNNEL_NAME}" "${DOMAIN}"

    # Also route www subdomain
    cloudflared tunnel route dns "${TUNNEL_NAME}" "www.${DOMAIN}"

    echo "✅ DNS routing configured"
    echo "Note: DNS propagation may take a few minutes"
}

# Function to create config file
create_config() {
    echo "📝 Creating tunnel configuration..."

    # Create config directory
    mkdir -p "${CONFIG_DIR}"

    # Get tunnel ID
    TUNNEL_ID=$(cloudflared tunnel list | grep "${TUNNEL_NAME}" | awk '{print $1}')

    if [[ -z "$TUNNEL_ID" ]]; then
        echo "❌ Error: Could not find tunnel ID"
        exit 1
    fi

    # Create config file
    cat > "${CONFIG_DIR}/config.yml" << EOF
tunnel: ${TUNNEL_ID}
credentials-file: ${CONFIG_DIR}/${TUNNEL_ID}.json

# Ingress rules - what to expose
ingress:
  # Main application (catches all traffic)
  - service: ${LOCAL_URL}
    originRequest:
      # Don't verify local SSL cert (we're using HTTP locally)
      noTLSVerify: true
      # Keep connections alive
      keepAliveConnections: 10
      # Timeout settings
      connectTimeout: 30s
      # Enable WebSocket support
      originServerName: localhost
EOF

    echo "✅ Configuration created at ${CONFIG_DIR}/config.yml"
}

# Function to create systemd service
create_systemd_service() {
    echo "🔧 Creating systemd service for auto-start..."

    # Create service file
    sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=Cloudflare Tunnel for ${DOMAIN}
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
User=pi
Group=pi
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate run
Restart=always
RestartSec=5
Environment="TUNNEL_ORIGIN_CERT=${CONFIG_DIR}/cert.pem"

[Install]
WantedBy=multi-user.target
EOF

    # Enable and start service
    sudo systemctl daemon-reload
    sudo systemctl enable ${SERVICE_NAME}

    echo "✅ Systemd service created and enabled"
}

# Function to start tunnel
start_tunnel() {
    echo "🚀 Starting Cloudflare tunnel..."

    # Check if Docker is running the app
    if ! docker compose -f /home/pi/plane-game-v4/infra/docker-compose.yml ps | grep -q "Up"; then
        echo "⚠️  Warning: Plane game Docker containers are not running"
        echo "Run: cd /home/pi/plane-game-v4 && docker compose -f infra/docker-compose.yml up -d"
    fi

    # Start the service
    sudo systemctl start ${SERVICE_NAME}

    # Check status
    sleep 3
    if sudo systemctl is-active --quiet ${SERVICE_NAME}; then
        echo "✅ Tunnel is running!"
        echo ""
        echo "🌍 Your game should now be accessible at:"
        echo "   https://${DOMAIN}"
        echo "   https://www.${DOMAIN}"
        echo ""
        echo "📊 Check tunnel status with:"
        echo "   sudo systemctl status ${SERVICE_NAME}"
        echo "   sudo journalctl -u ${SERVICE_NAME} -f"
    else
        echo "❌ Failed to start tunnel"
        echo "Check logs: sudo journalctl -u ${SERVICE_NAME} -n 50"
        exit 1
    fi
}

# Main execution
main() {
    echo "======================================"
    echo "Cloudflare Tunnel Setup for aeroguessr"
    echo "======================================"
    echo ""

    check_pi
    install_cloudflared
    authenticate_cloudflare
    create_tunnel
    configure_dns
    create_config
    create_systemd_service
    start_tunnel

    echo ""
    echo "✨ Setup complete!"
    echo ""
    echo "Useful commands:"
    echo "- Check status: sudo systemctl status ${SERVICE_NAME}"
    echo "- View logs: sudo journalctl -u ${SERVICE_NAME} -f"
    echo "- Restart tunnel: sudo systemctl restart ${SERVICE_NAME}"
    echo "- Stop tunnel: sudo systemctl stop ${SERVICE_NAME}"
    echo ""
    echo "Note: Make sure your Docker containers are running:"
    echo "cd /home/pi/plane-game-v4 && docker compose -f infra/docker-compose.yml up -d"
}

# Run main function
main
