#!/bin/bash
# Start Stage 2 (UAT/Pre-prod) Flask server on port 5053
export FLASK_ENV=uat
export STAGE=2
python3 frontend/terminal.py --port=5053 &
echo "Stage 2 (UAT/Pre-prod) server started on port 5053"