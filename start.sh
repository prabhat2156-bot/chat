#!/bin/bash
# Quick start script — runs bot directly in foreground (for testing)
# For permanent background service, use setup.sh instead

export BOT_TOKEN="${BOT_TOKEN:-YOUR_BOT_TOKEN_HERE}"

if [ "$BOT_TOKEN" = "YOUR_BOT_TOKEN_HERE" ]; then
    echo "ERROR: Set your bot token first:"
    echo "  export BOT_TOKEN=123456:ABC-your-token"
    exit 1
fi

echo "Starting VCF Contact Bot..."
python3 bot.py
