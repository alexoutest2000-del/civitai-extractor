#!/bin/bash
# Civitai Data Extractor — PySide6 GUI launcher
set -e
cd "$(dirname "$0")"

# Pick the right Python
PYTHON=""
for py in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$py" &>/dev/null; then
        PYTHON="$py"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: No Python 3 interpreter found"
    exit 1
fi
echo "Using $PYTHON ($($PYTHON --version))"

# Ensure venv is healthy
if [ ! -f ".venv/bin/python" ] || ! .venv/bin/python -c "import PySide6" 2>/dev/null; then
    rm -rf .venv
    echo "Creating virtual environment..."
    if ! $PYTHON -m venv .venv 2>/tmp/civitai-venv-err; then
        echo ""
        echo "ERROR: Could not create venv."
        echo "  Try:  sudo apt install python3-venv"
        echo ""
        echo "Details:"
        cat /tmp/civitai-venv-err
        rm -f /tmp/civitai-venv-err
        exit 1
    fi
    rm -f /tmp/civitai-venv-err
    echo "Installing PySide6 (this may take a minute)..."
    .venv/bin/pip install --quiet pyside6
    echo "Setup complete."
fi

exec .venv/bin/python gui_qt.py
