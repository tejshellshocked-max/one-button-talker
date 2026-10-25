"""
Camera calibration for One-Button Talker (about 20 seconds).

A voice tells you what to do, so you can follow along with your eyes closed:
  1. look at the screen normally
  2. look DOWN at the keyboard (eyes open)
  3. close your eyes until the beep
It measures YOUR eyes in each position and saves the best cutoff between
"looking down" and "closed" to calibration.json. The app uses it next time
it starts, so looking down no longer counts as a blink.

Run:  double-click "Calibrate Camera.command"   (or: python3 calibrate.py)
"""
import json
import subprocess
import sys
import time

import blink


def voice(text):
    print("\n>>> " + text)
    try:
        subprocess.run(["say", text])
    except FileNotFoundError:
        pass


def beep():
    try:
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"])
    except FileNotFoundError:
        print("*beep*")


def collect(cam, seconds, settle=1.0):
    """Gather one (ear, blink score) sample per new camera frame."""
    samples, last_seen = [], None
    start = time.time()
    while time.time() - start < settle + seconds:
        time.sleep(0.01)
        if cam.error:
            raise RuntimeError(cam.error)
        if time.time() - start < settle or cam._last == last_seen:
            continue
        last_seen = cam._last
        ear, bl, _ = cam.reading_full()
        if ear is not None:
            samples.append((ear, bl))
    return samples


def main():
    print(__doc__)
    cam = blink.EyeCamera()
    print("Starting the camera...")
    t0 = time.time()
    while cam.reading() is None:
        if cam.error:
            print("Camera problem:", cam.error)
            return 1
        if time.time() - t0 > 30:
            print("Can't see your face. Sit facing the camera with light on your face, then try again.")
            return 1
        time.sleep(0.1)

    try:
        voice("Calibration. Look at the screen normally.")
        open_s = collect(cam, 4)
        voice("Now look down at your keyboard. Keep your eyes open.")
        down_s = collect(cam, 4, settle=1.5)
        voice("Now close your eyes, and keep them closed until the beep.")
        closed_s = collect(cam, 3.5, settle=1.2)
        beep()
        voice("Open your eyes.")
    finally:
        cam.stop()

    if min(len(open_s), len(down_s), len(closed_s)) < 10:
        print("Not enough camera frames (face lost?). Try again with better light.")
        return 1

    c = blink.compute_calibration(open_s, down_s, closed_s)
    c["samples"] = [len(open_s), len(down_s), len(closed_s)]
    c["made"] = time.strftime("%Y-%m-%d %H:%M")
    with open(blink.CALIBRATION, "w") as f:
        json.dump(c, f, indent=2)

    print("\n  Your eyes            EAR (how open)")
    print(f"  looking at screen    {c['open_ear']:.3f}")
    print(f"  looking down         {c['down_ear']:.3f}")
    print(f"  closed               {c['closed_ear']:.3f}")
    print(f"\n  Using: {'blink score' if c['signal'] == 'blink' else 'eye openness (EAR)'}, "
          f"cutoff {c['threshold']}")
    if c["ok"]:
        voice("Done. Looking down will no longer count as a blink.")
    else:
        voice("Done, but looking down and closing your eyes look very similar to the camera.")
        print("  Tip: raise the laptop (or the camera) so it's level with your eyes,\n"
              "  then run this again. Looking down then looks much less like a blink.")
    print("\nSaved to calibration.json. Restart One-Button Talker to use it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
