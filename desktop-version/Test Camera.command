#!/bin/bash
# Checks blink tracking on its own. Double-click, look at the camera,
# and do a long blink: you should see "LONG BLINK = PRESS". Ctrl+C to stop.
cd "$(dirname "$0")"
PY=""
for c in python3 /usr/bin/python3 python3.13 python3.12 python3.11 python3.10; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import cv2, mediapipe" >/dev/null 2>&1; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then echo "No Python with opencv + mediapipe found."; read -p "Press Enter to close"; exit 1; fi
echo "Using $("$PY" --version 2>&1). Open eyes = big number, closed = small number."
"$PY" blink.py
