#!/bin/bash
# Starts One-Button Talker. Double-click to run.
cd "$(dirname "$0")"

# This Mac has more than one Python. Use the first one that has everything
# blink control needs (pygame + opencv + mediapipe).
PY=""
for c in python3 /usr/bin/python3 python3.13 python3.12 python3.11 python3.10; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import pygame, cv2, mediapipe" >/dev/null 2>&1; then
    PY="$c"; break
  fi
done

if [ -z "$PY" ]; then
  echo "Camera libraries not found - blink control will be OFF (SPACE still works)."
  PY=python3
  if ! "$PY" -c "import pygame" 2>/dev/null; then
    echo "Installing pygame (one-time)..."
    "$PY" -m pip install --user pygame || { echo; echo "pygame install failed - see message above."; read -p "Press Enter to close"; exit 1; }
  fi
fi

# small library for the caregiver-link QR code (optional - skip if it fails)
"$PY" -c "import qrcode" 2>/dev/null || "$PY" -m pip install --user -q qrcode >/dev/null 2>&1

echo "Using $("$PY" --version 2>&1) ($(command -v "$PY"))"
echo "Starting One-Button Talker... (SPACE or a long blink to select, H for help)"
"$PY" talker.py
echo "Talker closed."
