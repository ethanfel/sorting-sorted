#!/bin/bash

# 1. Navigate to app directory
cd /app

# 2. Install dependencies (Including NiceGUI if missing)
# This checks your requirements.txt AND ensures nicegui is present
pip install --no-cache-dir -r requirements.txt

# 3. Start NiceGUI in the Background (&)
# This runs silently while the script continues
echo "🚀 Starting NiceGUI on Port 8080..."
python3 gallery_app.py &

# 4. Start Streamlit in the Foreground
# This keeps the container running
echo "🚀 Starting Streamlit on Port 8501..."
streamlit run app.py --server.port=8501 --server.address=0.0.0.0