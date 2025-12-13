#!/bin/bash

# Activate virtual environment
source venv/bin/activate

# Run the API server
python backend/api.py --mode http --host 127.0.0.1 --port 5000

