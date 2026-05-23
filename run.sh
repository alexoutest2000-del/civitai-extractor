#!/bin/bash
# Civitai Data Extractor — PySide6 GUI launcher
set -e
cd "$(dirname "$0")"

# Create venv if missing
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    if ! python3 -m venv .venv 2>/dev/null; then
        echo ""
        echo "ERROR: python3-venv is not installed."
        echo "Run:  sudo apt install python3.14-venv"
        echo "Then: ./run.sh"
        exit 1
    fi
    echo "Installing PySide6 (this may take a minute)..."
    .venv/bin/pip install --quiet pyside6
    echo "Setup complete."
fi

exec .venv/bin/python gui_qt.py
