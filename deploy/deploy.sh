#!/bin/bash
# Crypto Signal Bot v3 - VPS Deployment Script
# Usage: ./deploy.sh

set -e

echo "========================================="
echo "  Crypto Signal Bot v3 - VPS Deploy"
echo "========================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    log_error "Please run as root (sudo ./deploy.sh)"
    exit 1
fi

# Update system
log_info "Updating system..."
apt update && apt upgrade -y

# Install dependencies
log_info "Installing dependencies..."
apt install -y python3.11 python3.11-venv python3-pip git nginx certbot python3-certbot-nginx ufw fail2ban curl wget

# Create app directory
log_info "Creating app directory..."
mkdir -p /opt/crypto-bot
cd /opt/crypto-bot

# Copy project files
log_info "Copying project files..."
cp -r /tmp/crypto-bot-source/* /opt/crypto-bot/

# Create .env if not exists
if [ ! -f .env ]; then
    log_info "Creating .env file..."
    cp .env.example .env
    log_warn "Please edit .env with your credentials!"
    nano .env
fi

# Set permissions
chmod 600 .env
chown root:root .env

# Create virtual environment
log_info "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create directories
mkdir -p data logs results

# Create systemd service
log_info "Creating systemd service..."
cat > /etc/systemd/system/crypto-bot.service << 'EOF'
[Unit]
Description=Crypto Signal Bot v3
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/crypto-bot
Environment="PATH=/opt/crypto-bot/venv/bin"
ExecStart=/opt/crypto-bot/venv/bin/python main.py --log-level=INFO
Restart=always
RestartSec=10
StandardOutput=append:/opt/crypto-bot/logs/systemd.log
StandardError=append:/opt/crypto-bot/logs/systemd.err.log

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
log_info "Enabling and starting service..."
systemctl daemon-reload
systemctl enable crypto-bot
systemctl start crypto-bot

# Configure Nginx
log_info "Configuring Nginx..."
cat > /etc/nginx/sites-available/crypto-bot << 'EOF'
server {
    listen 80;
    server_name _;
    
    access_log /var/log/nginx/crypto-bot-access.log;
    error_log /var/log/nginx/crypto-bot-error.log;
    
    location / {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        proxy_buffering off;
    }
    
    location /ws {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }
}
EOF

ln -sf /etc/nginx/sites-available/crypto-bot /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# Configure firewall
log_info "Configuring firewall..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
echo "y" | ufw enable

# Install Fail2Ban
log_info "Configuring Fail2Ban..."
systemctl enable fail2ban
systemctl start fail2ban

# Create healthcheck script
log_info "Creating healthcheck script..."
mkdir -p /opt/crypto-bot/scripts
cat > /opt/crypto-bot/scripts/healthcheck.sh << 'EOF'
#!/bin/bash
if ! systemctl is-active --quiet crypto-bot; then
    echo "$(date): Bot is down! Restarting..." >> /opt/crypto-bot/logs/healthcheck.log
    systemctl restart crypto-bot
fi
if ! systemctl is-active --quiet nginx; then
    echo "$(date): Nginx is down! Restarting..." >> /opt/crypto-bot/logs/healthcheck.log
    systemctl restart nginx
fi
EOF
chmod +x /opt/crypto-bot/scripts/healthcheck.sh

# Add to cron
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/crypto-bot/scripts/healthcheck.sh") | crontab -

# Summary
echo ""
echo "========================================="
log_info "Deployment completed!"
echo "========================================="
echo ""
echo "Service Status:"
systemctl status crypto-bot --no-pager
echo ""
echo "Nginx Status:"
systemctl status nginx --no-pager
echo ""
echo "Logs:"
echo "  - Bot: tail -f /opt/crypto-bot/logs/bot.log"
echo "  - System: journalctl -u crypto-bot -f"
echo "  - Nginx: tail -f /var/log/nginx/crypto-bot-access.log"
echo ""
echo "Commands:"
echo "  - Start: systemctl start crypto-bot"
echo "  - Stop: systemctl stop crypto-bot"
echo "  - Restart: systemctl restart crypto-bot"
echo "  - Status: systemctl status crypto-bot"
echo ""
echo "Access:"
echo "  - Dashboard: http://$(hostname -I | awk '{print $1}')/dashboard"
echo "  - API: http://$(hostname -I | awk '{print $1}')/health"
echo ""
log_warn "Don't forget to:"
log_warn "  1. Edit .env with your credentials"
log_warn "  2. Restart the bot: systemctl restart crypto-bot"
log_warn "  3. Set up SSL: certbot --nginx"
echo ""
