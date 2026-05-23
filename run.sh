#!/bin/bash
# Civitai Data Extractor — PySide6 GUI launcher
cd "$(dirname "$0")"

# Create venv if missing
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install pyside6
fi

exec .venv/bin/python gui_qt.py
