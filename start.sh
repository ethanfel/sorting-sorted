#!/bin/bash

# NiceSorter - Start Script
# Runs the NiceGUI gallery interface on port 8080

set -e

# Navigate to app directory if running in container
if [ -d "/app" ]; then
    cd /app
fi

# Install dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "📦 Installing dependencies..."
    pip install --no-cache-dir -q -r requirements.txt
fi

# Initialize database
echo "🗄️ Initializing database..."
python3 -c "from engine import SorterEngine; SorterEngine.init_db()"

# Start NiceGUI
echo "🚀 Starting NiceSorter on http://0.0.0.0:8080"
exec python3 gallery_app.py
