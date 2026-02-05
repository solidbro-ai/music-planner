#!/bin/bash
# Start Music Planner Dashboard

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check for Flask and dependencies
if ! python3 -c "import flask; import werkzeug" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install flask pyyaml werkzeug
fi

echo "🎵 Starting Music Planner Dashboard..."
echo "   http://localhost:5555"
echo ""

python3 app.py
