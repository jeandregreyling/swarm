#!/bin/bash
# Start Stage 3 (DEV) Flask server on port from $PORT
export FLASK_ENV=development
export STAGE=DEV
export PORT=${PORT:-5051}
python3 frontend/terminal.py &
echo "Stage 3 (DEV) server started on port $PORT"