"""
Blink-to-select for One-Button Talker.

The camera runs in a separate process (camera_worker.py) that sends this
file one number per frame: the Eye Aspect Ratio (EAR), how open the eyes are.
This file turns a LONG blink into one button press.

Test it on its own:  python3 blink.py   (prints your EAR live, Ctrl+C to stop)
"""
import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "camera_worker.py")

# Tej's calibration: open eye ~0.52, closed eye ~0.06
EAR_THRESHOLD = 0.25   # below this = eye closed (until it learns this person)
HOLD_SECONDS = 0.35    # eye must stay closed this long to count as a "press" (normal blinks ~0.1-0.15 s)
STALE_SECONDS = 1.0    # no camera news for this long = don't trust the old number
LOOK_DOWN = 0.35       # face model's "looking down" score above this = eyes aimed down
CALIBRATION = os.path.join(HERE, "calibration.json")


def percentile(values, p):
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def compute_calibration(open_s, down_s, closed_s):
    """Pick the best way to tell CLOSED eyes from eyes LOOKING DOWN, for this person.

    Each list holds (ear, blink_score) samples. Two possible signals:
      - EAR (lid shape): closed is LOW, looking down is a bit higher
      - blink score: closed is HIGH, looking down is a bit lower
    We measure the gap between "looking down" and "closed" for each signal
    (using the worst 10% of samples so it's safe) and use the one with the
    bigger gap, with the cutoff right in the middle of that gap.
    """
    ear = lambda s: [x[0] for x in s]
    bl = lambda s: [x[1] for x in s if x[1] is not None]
    result = {"open_ear": percentile(ear(open_s), 50),
              "down_ear": percentile(ear(down_s), 50),
              "closed_ear": percentile(ear(closed_s), 50)}
    span = max(1e-6, result["open_ear"] - result["closed_ear"])
    ear_gap = (percentile(ear(down_s), 10) - percentile(ear(closed_s), 90)) / span
    best = ("ear", ear_gap, (percentile(ear(down_s), 10) + percentile(ear(closed_s), 90)) / 2)
    if bl(down_s) and bl(closed_s) and bl(open_s):
        bspan = max(1e-6, percentile(bl(closed_s), 50) - percentile(bl(open_s), 50))
        bl_gap = (percentile(bl(closed_s), 10) - percentile(bl(down_s), 90)) / bspan
        if bl_gap > ear_gap:
            best = ("blink", bl_gap, (percentile(bl(closed_s), 10) + percentile(bl(down_s), 90)) / 2)
    result.update(signal=best[0], gap=round(best[1], 3), threshold=round(best[2], 4),
                  ok=best[1] > 0)
    if not result["ok"]:
        # the camera can't separate them: use the middle of the typical values
        result["threshold"] = round((result["down_ear"] + result["closed_ear"]) / 2, 4)
        result["signal"] = "ear"
    return result


def load_calibration():
    try:
        with open(CALIBRATION) as f:
            c = json.load(f)
        if isinstance(c, dict) and c.get("signal") in ("ear", "blink") \
                and isinstance(c.get("threshold"), (int, float)):
            return c
    except (OSError, ValueError):
        pass
    return None


def _log_file():
    """Camera library messages go to camera_log.txt (handy for fixing problems)."""
    try:
        return open(os.path.join(HERE, "camera_log.txt"), "w")
    except OSError:
        return subprocess.DEVNULL


class EyeCamera:
    """Starts camera_worker.py and keeps the latest reading from it."""

    def __init__(self, python=None):
        self.ear = None            # latest EAR, or None
        self.blink_score = None    # face model's eye-blink score 0-1 (if available)
        self.look_down = None      # face model's looking-down score 0-1 (if available)
        self.face = None           # True = eyes found, False = no face, None = not running yet
        self.message = "camera starting..."
        self.error = None
        self._last = 0.0
        self.proc = subprocess.Popen(
            [python or sys.executable, "-u", WORKER],
            stdout=subprocess.PIPE, stderr=_log_file(), text=True,
            cwd=HERE)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            kind, _, rest = line.strip().partition(" ")
            if kind == "EAR":
                parts = rest.split()
                try:
                    self.ear = float(parts[0])
                    extra = dict(zip(parts[1::2], map(float, parts[2::2])))
                except (ValueError, IndexError):
                    continue
                self.blink_score = extra.get("BL")
                self.look_down = extra.get("LD")
                self.face, self._last = True, time.time()
                self.message = "eyes tracked"
            elif kind == "NOFACE":
                self.ear, self.face, self._last = None, False, time.time()
                self.message = "face not found"
            elif kind == "STATUS":
                self.message = rest
            elif kind == "ERROR":
                self.error = rest
        if not self.error:
            self.error = "camera stopped"
        self.ear, self.face = None, None

    def reading(self):
        """The latest EAR, or None if there's no fresh reading."""
        if self.ear is not None and time.time() - self._last < STALE_SECONDS:
            return self.ear
        return None

    def reading_full(self):
        """(EAR, blink score, look-down score) - all None if there's no fresh reading."""
        if self.reading() is None:
            return None, None, None
        return self.ear, self.blink_score, self.look_down

    def stop(self):
        try:
            self.proc.terminate()
        except Exception:
            pass


class BlinkButton:
    """Turns a long, deliberate blink into one button press.

    Normal blinks (~0.1-0.15 s) are ignored. One long blink = one press,
    even if the eye stays closed longer; the eye must open again before
    the next press can happen.

    Auto-calibration: everyone's eyes are different (and glasses change the
    numbers), so it learns this person's normal open-eye value as they use it
    and sets the "closed" line at about half of that.
    """

    def __init__(self, calibration="load"):
        self.closed_time = 0.0
        self.fired = False
        self.open_baseline = None      # learned open-eye EAR
        self.calibration = load_calibration() if calibration == "load" else calibration

    @property
    def threshold(self):
        if self.open_baseline is None:
            return EAR_THRESHOLD
        return max(0.12, 0.5 * self.open_baseline)

    def eye_closed(self, ear, blink=None, down=None):
        if ear is None:
            return False
        c = self.calibration
        if c:                                       # this person's own measured cutoff
            if c["signal"] == "blink" and blink is not None:
                return blink > c["threshold"]
            if c["signal"] == "ear":
                return ear < c["threshold"]
        if down is not None and down > LOOK_DOWN:
            # looking down makes the lids drop: demand a much deeper closure
            base = self.open_baseline or (2 * EAR_THRESHOLD)
            return ear < max(0.08, 0.28 * base)
        return ear < self.threshold

    def _learn(self, ear, down=None):
        # only learn from clearly-open frames, slowly, so blinks don't skew it
        if ear is None or ear < self.threshold * 1.3:
            return
        if down is not None and down > LOOK_DOWN:   # don't learn while looking down
            return
        if self.open_baseline is None:
            self.open_baseline = ear
        else:
            self.open_baseline += 0.02 * (ear - self.open_baseline)

    def update(self, ear, dt, blink=None, down=None):
        """Call every frame. Returns True exactly once per long blink."""
        self._learn(ear, down)
        if self.eye_closed(ear, blink, down):
            self.closed_time += dt
            if self.closed_time >= HOLD_SECONDS and not self.fired:
                self.fired = True
                return True
        else:
            self.closed_time = 0.0
            self.fired = False
        return False


if __name__ == "__main__":
    cam = EyeCamera()
    button = BlinkButton()
    last = time.time()
    try:
        while True:
            time.sleep(0.05)
            now = time.time()
            ear, bl, ld = cam.reading_full()
            if button.update(ear, now - last, bl, ld):
                print("   *** LONG BLINK = PRESS ***")
            last = now
            if cam.error:
                print("ERROR:", cam.error)
                break
            if ear is None:
                print(cam.message)
            else:
                extra = f"  blink {bl:.2f}  look-down {ld:.2f}" if bl is not None else ""
                state = "CLOSED" if button.eye_closed(ear, bl, ld) else "open"
                print(f"eyes {ear:.3f}{extra}   -> {state}")
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop()
