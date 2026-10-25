"""
Gaze test: shows roughly where you're looking, using the iris position.
Run:  python3 gaze_test.py      (Ctrl+C to stop)
Look far LEFT, CENTER, then far RIGHT of the screen and watch the number.
"""
import time
import cv2
import mediapipe as mp
import blink   # reuses the camera + face model from blink.py

CORNER_A, CORNER_B, IRIS = 33, 133, 468   # eye corners + iris center (same eye)

while True:
    ok, frame = blink.camera.read()
    if not ok:
        continue
    image = mp.Image(image_format=mp.ImageFormat.SRGB,
                     data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    result = blink.landmarker.detect_for_video(
        image, int((time.time() - blink._start) * 1000))
    if not result.face_landmarks:
        continue
    lm = result.face_landmarks[0]
    # 0.0 = iris at one corner, 1.0 = iris at the other corner, ~0.5 = middle
    ratio = (lm[IRIS].x - lm[CORNER_A].x) / (lm[CORNER_B].x - lm[CORNER_A].x)
    bar = " " * int(ratio * 40) + "O"
    print(f"{ratio:5.2f} |{bar:<41}|")
