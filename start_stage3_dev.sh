#!/bin/bash
# Start Stage 3 (DEV) Flask server on port 5051
export FLASK_ENV=development
export STAGE=3
python3 frontend/terminal.py --port=5051 &
echo "Stage 3 (DEV) server started on port 5051"