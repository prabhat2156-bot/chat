#!/bin/bash
# ============================================================
# VCF Contact Bot — VPS Setup Script
# Run once on your VPS to install and register as a service
# Usage: bash setup.sh YOUR_BOT_TOKEN_HERE
# ============================================================

set -e

TOKEN="$1"
INSTALL_DIR="/opt/vcfbot"

if [ -z "$TOKEN" ]; then
    echo "Usage: bash setup.sh YOUR_BOT_TOKEN"
    echo "Example: bash setup.sh 123456:ABC-your-token"
    exit 1
fi

echo "=== Installing VCF Contact Bot ==="

# Install Python if needed
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv

# Create install directory
mkdir -p "$INSTALL_DIR"
cp bot.py "$INSTALL_DIR/"
cp requirements.txt "$INSTALL_DIR/"

# Create virtual environment and install deps
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r requirements.txt -q

# Write systemd service with the provided token
cat > /etc/systemd/system/vcfbot.service <<EOF
[Unit]
Description=VCF Contact Telegram Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python bot.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=BOT_TOKEN=$TOKEN

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
systemctl daemon-reload
systemctl enable vcfbot
systemctl start vcfbot

echo ""
echo "=== Done! Bot is running as a background service ==="
echo ""
echo "Useful commands:"
echo "  systemctl status vcfbot       — check if running"
echo "  journalctl -u vcfbot -f       — watch live logs"
echo "  systemctl restart vcfbot      — restart bot"
echo "  systemctl stop vcfbot         — stop bot"
