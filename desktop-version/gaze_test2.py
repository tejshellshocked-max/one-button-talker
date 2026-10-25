"""
Better gaze test: both eyes averaged + smoothing, plus head-turn.
Run:  python3 gaze_test2.py     (Ctrl+C to stop)
Do the same left / hand / center / hand / right test as before.
  EYES = iris position (move only your eyes)
  HEAD = head turn     (try turning your head a little too)
"""
import time
import cv2
import mediapipe as mp
import blink

# (corner, corner, iris center) for each eye
EYES = [(33, 133, 468), (362, 263, 473)]
NOSE, LEFT_CHEEK, RIGHT_CHEEK = 1, 234, 454

smooth_eye = smooth_head = None
ALPHA = 0.3   # smoothing: lower = steadier but slower

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

    ratios = []
    for a, b, iris in EYES:
        left, right = sorted([lm[a].x, lm[b].x])
        ratios.append((lm[iris].x - left) / (right - left))
    eye = sum(ratios) / len(ratios)

    # head turn: where the nose sits between the two sides of the face
    head = (lm[NOSE].x - lm[LEFT_CHEEK].x) / (lm[RIGHT_CHEEK].x - lm[LEFT_CHEEK].x)

    smooth_eye = eye if smooth_eye is None else smooth_eye + ALPHA * (eye - smooth_eye)
    smooth_head = head if smooth_head is None else smooth_head + ALPHA * (head - smooth_head)
    print(f"EYES {smooth_eye:5.2f}   HEAD {smooth_head:5.2f}")
