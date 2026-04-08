#!/bin/bash
# Start Stage 1 (Production) Flask server on port 5050
export FLASK_ENV=production
export STAGE=1
python3 frontend/terminal.py --port=5050 &
echo "Stage 1 (Production) server started on port 5050"