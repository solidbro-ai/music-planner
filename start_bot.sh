#!/bin/bash
# Start the Music Planner Telegram Bot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables
if [[ -f .env ]]; then
    export $(grep -v '^#' .env | xargs)
fi

# Check for required token
if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
    echo "❌ TELEGRAM_BOT_TOKEN not set"
    echo "Create a .env file with your token (see .env.example)"
    exit 1
fi

# Check for python3
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 not found"
    exit 1
fi

# Install dependencies if needed
python3 -c "import telegram" 2>/dev/null || {
    echo "📦 Installing python-telegram-bot..."
    pip3 install python-telegram-bot --quiet
}

echo "🎵 Starting Music Planner Telegram Bot..."
echo "Press Ctrl+C to stop"
echo ""

python3 telegram_bot.py
