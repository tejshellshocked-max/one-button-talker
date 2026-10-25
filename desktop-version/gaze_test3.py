"""
Gaze test 3: sharper camera + head compensation + calibration.
Run:  python3 gaze_test3.py
It will ask you to look CENTER, then LEFT, then RIGHT (press Enter for each).
Then it shows which zone it thinks you're looking at, live. Ctrl+C to stop.
Keep your head as still as you can, move only your eyes.
"""
import time
import cv2
import mediapipe as mp
import blink

# Fix 1: higher camera resolution -> more pixels on the iris
blink.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
blink.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

EYES = [(33, 133, 468), (362, 263, 473)]
NOSE, L_CHEEK, R_CHEEK = 1, 234, 454


def measure():
    """Return (eye ratio, head ratio) for one frame, or None."""
    ok, frame = blink.camera.read()
    if not ok:
        return None
    image = mp.Image(image_format=mp.ImageFormat.SRGB,
                     data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    r = blink.landmarker.detect_for_video(image, int((time.time() - blink._start) * 1000))
    if not r.face_landmarks:
        return None
    lm = r.face_landmarks[0]
    ratios = []
    for a, b, iris in EYES:
        lo, hi = sorted([lm[a].x, lm[b].x])
        ratios.append((lm[iris].x - lo) / (hi - lo))
    head = (lm[NOSE].x - lm[L_CHEEK].x) / (lm[R_CHEEK].x - lm[L_CHEEK].x)
    return sum(ratios) / 2, head


def average(seconds=2.0):
    """Average many frames for a steady reading."""
    eyes, heads, end = [], [], time.time() + seconds
    while time.time() < end:
        m = measure()
        if m:
            eyes.append(m[0]); heads.append(m[1])
    return sum(eyes) / len(eyes), sum(heads) / len(heads)


# Fix 2: calibration (learn THIS person's numbers)
cal = {}
for spot in ["CENTER", "LEFT", "RIGHT"]:
    input(f"Look at the {spot} of the screen (eyes only), then press Enter...")
    cal[spot] = average()
    print(f"  {spot}: eyes {cal[spot][0]:.3f}  head {cal[spot][1]:.3f}")

# Fix 3: head compensation - estimate how much the eye number shifts when
# the head turns, using the head's offset from center during calibration.
c_eye, c_head = cal["CENTER"]
HEAD_GAIN = 0.0   # start with none; printed numbers show if head drift matters

left_gap = abs(cal["LEFT"][0] - c_eye)
right_gap = abs(cal["RIGHT"][0] - c_eye)
print(f"\nGap center->left: {left_gap:.3f}   center->right: {right_gap:.3f}")
print("Bigger than ~0.04 = usable. Now live (Ctrl+C to stop):\n")

smooth = None
while True:
    m = measure()
    if not m:
        continue
    eye = m[0] - HEAD_GAIN * (m[1] - c_head)
    smooth = eye if smooth is None else smooth + 0.25 * (eye - smooth)
    # pick whichever calibrated spot is closest
    zone = min(cal, key=lambda k: abs(cal[k][0] - smooth))
    print(f"eyes {smooth:.3f}  head {m[1]:.2f}  ->  {zone}")
