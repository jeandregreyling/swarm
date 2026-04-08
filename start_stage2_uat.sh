#!/bin/bash
# Start Stage 2 (UAT/Pre-prod) Flask server on port from $PORT
export FLASK_ENV=uat
export STAGE=UAT
export PORT=${PORT:-5053}
python3 frontend/terminal.py &
echo "Stage 2 (UAT/Pre-prod) server started on port $PORT"