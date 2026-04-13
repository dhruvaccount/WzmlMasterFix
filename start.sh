#!/bin/bash

set -e

echo "========================================"
echo "WZML-X v4.0.0 Starting..."
echo "========================================"

if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

if [ -f update.py ]; then
    echo "Running update check..."
    python3 update.py || true
fi

echo "Starting WZML-X..."
python3 main.py