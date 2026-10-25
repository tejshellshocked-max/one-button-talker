#!/bin/bash
# Installs the eye-tracking library for Python 3.13 and runs the gaze grid test.
cd "$(dirname "$0")"
if ! command -v python3.13 >/dev/null; then
  echo "Python 3.13 not found. Install it from https://www.python.org/downloads/ first."
  read -p "Press Enter to close"; exit 1
fi
echo "Installing eye-tracking packages (one time, a few minutes)..."
python3.13 -m pip install --upgrade pip >/dev/null
python3.13 -m pip install eyeGestures pygame opencv-python mediapipe || { read -p "Install failed - press Enter"; exit 1; }
echo "Starting gaze test... (ESC to quit)"
python3.13 gaze_grid.py
