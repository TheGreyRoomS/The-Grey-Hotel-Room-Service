#!/bin/bash
# ──────────────────────────────────────────────────────────
#  Hotel Room Service App — Start Script
#  Run this once to set up, then again to start the server
# ──────────────────────────────────────────────────────────

echo "🏨 Boutique Hotel Room Service App"
echo "──────────────────────────────────"

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 is required. Install from python.org"
  exit 1
fi

# Install dependencies
echo "Installing dependencies..."
pip3 install tornado PyJWT --break-system-packages 2>/dev/null || \
pip3 install tornado PyJWT 2>/dev/null || \
pip install tornado PyJWT 2>/dev/null

# Start server
echo ""
echo "Starting server on http://localhost:8080"
echo "Press Ctrl+C to stop"
echo ""
python3 server.py
