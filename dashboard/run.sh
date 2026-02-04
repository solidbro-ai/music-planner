#!/bin/bash
# Start Music Planner Dashboard

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check for Flask
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Installing Flask..."
    pip3 install flask pyyaml
fi

echo "🎵 Starting Music Planner Dashboard..."
echo "   http://localhost:5555"
echo ""

python3 app.py
