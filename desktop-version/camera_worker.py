"""
Camera worker for One-Button Talker (runs as its OWN process).

Why a separate process: the camera library (OpenCV) and the window library
(pygame) each bring their own copy of SDL. Loaded together in one program,
macOS warns about "mysterious crashes" and the camera can stop working.
Running the camera here, in its own process, keeps them apart. It also
means a slow camera frame can never freeze the scanning.

It prints one line per camera frame:
    EAR 0.412 BL 0.08 LD 0.31
                   eyes found. EAR = how open the eyes are (shape of the lids);
                   BL = the face model's "eye blink" score (0-1);
                   LD = its "eyes looking down" score (0-1). Looking down
                   makes the lids drop, so EAR alone can mistake it for a blink.
    NOFACE         camera works, but no face in view
    STATUS <text>  progress messages (starting, which camera, ...)
    ERROR <text>   something is wrong (then it exits)
"""
import math
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "face_landmarker.task")
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/latest/face_landmarker.task")

# MediaPipe landmark numbers for the 6 points around each eye:
# p1, p2, p3, p4, p5, p6   (p1 & p4 = corners, p2/p3 = top, p6/p5 = bottom)
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]


def say(line):
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except (BrokenPipeError, OSError):      # the app closed: stop too
        sys.exit(0)


def one_eye_ear(p):
    """EAR = (dist(p2,p6) + dist(p3,p5)) / (2 * dist(p1,p4))"""
    width = math.dist(p[0], p[3])
    if width == 0:
        return 0.0
    return (math.dist(p[1], p[5]) + math.dist(p[2], p[4])) / (2 * width)


def open_camera(cv2):
    """Try camera 0, 1, 2 and keep the first one that really gives pictures.
    (On Macs, number 0 is sometimes an iPhone 'Continuity Camera' or a
    camera that's busy in another app.)"""
    fallback = None                  # a camera that works but looked dark
    for index in (0, 1, 2):
        cam = cv2.VideoCapture(index)
        if not cam.isOpened():
            cam.release()
            continue
        start, got_frames = time.time(), False
        while time.time() - start < 3:
            ok, frame = cam.read()
            if ok and frame is not None:
                got_frames = True
                if frame.mean() > 3:            # a real (not black) picture
                    say(f"STATUS using camera {index}")
                    if fallback is not None:
                        fallback[1].release()
                    return cam
            time.sleep(0.05)
        if got_frames and fallback is None:
            fallback = (index, cam)
        else:
            cam.release()
    if fallback is not None:
        say(f"STATUS using camera {fallback[0]} (picture looks dark - add light)")
        return fallback[1]
    return None


def main():
    say("STATUS loading face model...")
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision
    except ImportError as e:
        say(f"ERROR missing library ({e.name}) - see README to install")
        return

    if not os.path.exists(MODEL_PATH):
        say("STATUS downloading face model (one time)...")
        try:
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH + ".part")
            os.replace(MODEL_PATH + ".part", MODEL_PATH)
        except Exception:
            say("ERROR could not download the face model - check internet")
            return

    landmarker = None
    for shapes in (True, False):       # blink/look-down scores if the model has them
        try:
            landmarker = vision.FaceLandmarker.create_from_options(
                vision.FaceLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=MODEL_PATH),
                    running_mode=vision.RunningMode.VIDEO,
                    num_faces=1,
                    output_face_blendshapes=shapes,
                ))
            break
        except Exception as e:
            err = e
    if landmarker is None:
        say(f"ERROR face model would not load ({err})")
        return

    say("STATUS opening camera...")
    cam = open_camera(cv2)
    if cam is None:
        say("ERROR no camera picture - allow Terminal in System Settings > "
            "Privacy & Security > Camera, and close other apps using the camera")
        return

    start = time.monotonic()
    last_ts = -1
    bad_frames = 0
    parent = os.getppid()
    while True:
        if os.getppid() != parent:          # app was closed
            return
        ok, frame = cam.read()
        if not ok or frame is None:
            bad_frames += 1
            if bad_frames > 60:
                say("ERROR the camera stopped sending pictures")
                return
            time.sleep(0.03)
            continue
        bad_frames = 0
        ts = int((time.monotonic() - start) * 1000)
        if ts <= last_ts:                   # MediaPipe needs increasing times
            ts = last_ts + 1
        last_ts = ts
        image = mp.Image(image_format=mp.ImageFormat.SRGB,
                         data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        result = landmarker.detect_for_video(image, ts)
        if not result.face_landmarks:
            say("NOFACE")
            continue
        lm = result.face_landmarks[0]
        left = [(lm[i].x, lm[i].y) for i in LEFT_EYE]
        right = [(lm[i].x, lm[i].y) for i in RIGHT_EYE]
        # average both eyes: steadier, and a wink still counts
        line = f"EAR {(one_eye_ear(left) + one_eye_ear(right)) / 2:.4f}"
        shapes = getattr(result, "face_blendshapes", None)
        if shapes:
            score = {c.category_name: c.score for c in shapes[0]}
            blink = (score.get("eyeBlinkLeft", 0) + score.get("eyeBlinkRight", 0)) / 2
            down = (score.get("eyeLookDownLeft", 0) + score.get("eyeLookDownRight", 0)) / 2
            line += f" BL {blink:.3f} LD {down:.3f}"
        say(line)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
