// One-Button Talker - blink control with the front camera.
//
// Google's MediaPipe face model finds 478 points on the face, every frame,
// right on the phone (nothing is uploaded). From those we measure:
//   EAR  - "eye aspect ratio": eyelid gap / eye width. Open ~0.3+, closed ~0.05
//   blink - the model's own "eye blink" score, 0..1
//   down  - the model's "eyes looking down" score, 0..1
// Looking down lowers the eyelids, so EAR alone can mistake it for a blink.
// When the eyes are aimed down we demand a much deeper closure, and a short
// calibration can measure this person's own "looking down" vs "closed".

import { FaceLandmarker, FilesetResolver } from "./vendor/mediapipe/vision_bundle.mjs";
import { load } from "./data.js";

const LEFT_EYE = [33, 160, 158, 133, 153, 144];   // p1..p6 (corners p1,p4)
const RIGHT_EYE = [362, 385, 387, 263, 373, 380];

export const HOLD_SECONDS = 0.35;   // a deliberate blink; normal blinks are ~0.1-0.15 s
export const WAKE_SECONDS = 1.5;    // hold this long to wake from REST
const EAR_START = 0.2;              // "closed" line until we learn this person's eyes
const BLINK_SCORE = 0.55;            // face model's "eyes closed" score that counts as closed
const STRONG_BLINK = 0.7;            // ...and this is "certainly closed", even after calibration
const LOOK_DOWN = 0.35;            // looking-down score above this = eyes aimed down
const STALE_MS = 1000;
const OPEN_GRACE = 0.1;            // eyes must be open this long to end a blink

function dist(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}
function eyeEAR(p) {
  const w = dist(p[0], p[3]);
  return w ? (dist(p[1], p[5]) + dist(p[2], p[4])) / (2 * w) : 0;
}

export class EyeTracker {
  constructor(video) {
    this.video = video;
    this.status = "off";          // off | starting | tracked | noface | error
    this.message = "camera off";
    this.ear = this.blink = this.down = null;
    this.lastSeen = 0;
    this.frameId = 0;             // goes up for each new face reading
    this._lastTime = -1;
  }

  async start() {
    this.status = "starting";
    this.message = "starting camera…";
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
    } catch (e) {
      this.status = "error";
      this.message = e && e.name === "NotAllowedError"
        ? "camera blocked - allow it in your browser settings" : "no camera found";
      return false;
    }
    this.video.srcObject = this.stream;
    this.video.setAttribute("playsinline", "");
    this.video.muted = true;
    try { await this.video.play(); } catch (e) { /* plays once frames arrive */ }

    this.message = "loading face model…";
    try {
      const fileset = await FilesetResolver.forVisionTasks("./vendor/mediapipe/wasm");
      const make = (delegate) => FaceLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: "./models/face_landmarker.task", delegate },
        runningMode: "VIDEO",
        numFaces: 1,
        outputFaceBlendshapes: true,
      });
      this._remake = make;
      try {
        this.model = await make("GPU");
      } catch (e) {
        this.model = await make("CPU");      // some phones/browsers have no GPU support
        this._remake = null;
      }
    } catch (e) {
      this.status = "error";
      this.message = "face model failed to load";
      console.error(e);
      return false;
    }
    this.status = "noface";
    this.message = "looking for your face…";
    return true;
  }

  stop() {
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.status = "off";
    this.message = "camera off";
    this.ear = this.blink = this.down = null;
  }

  // Call every animation frame. Runs the face model when there's a new video frame.
  step() {
    if (!this.model || !this.stream) return;
    const v = this.video;
    if (v.readyState < 2 || v.currentTime === this._lastTime) return;
    this._lastTime = v.currentTime;
    let r;
    try {
      r = this.model.detectForVideo(v, performance.now());
      this._errors = 0;
    } catch (e) {
      // some browsers create the GPU model fine but then fail every frame: switch to CPU
      this._errors = (this._errors || 0) + 1;
      if (this._errors === 15 && this._remake) {
        this.message = "switching face model…";
        const remake = this._remake; this._remake = null; this.model = null;
        remake("CPU").then((m) => { this.model = m; this._errors = 0; this.message = "looking for your face…"; })
          .catch(() => { this.status = "error"; this.message = "face model failed - try Chrome or Safari"; });
      }
      return;
    }
    const now = performance.now();
    if (!r.faceLandmarks || !r.faceLandmarks.length) {
      this.ear = this.blink = this.down = null;
      this.status = "noface";
      this.message = "face not found";
      this.lastSeen = now;
      return;
    }
    const lm = r.faceLandmarks[0];
    const W = v.videoWidth || 640, H = v.videoHeight || 480;
    const pts = (ids) => ids.map((i) => [lm[i].x * W, lm[i].y * H]);   // real pixel shape
    this.ear = (eyeEAR(pts(LEFT_EYE)) + eyeEAR(pts(RIGHT_EYE))) / 2;
    this.blink = this.down = null;
    if (r.faceBlendshapes && r.faceBlendshapes.length) {
      const s = {};
      for (const c of r.faceBlendshapes[0].categories) s[c.categoryName] = c.score;
      this.blink = ((s.eyeBlinkLeft || 0) + (s.eyeBlinkRight || 0)) / 2;
      this.down = ((s.eyeLookDownLeft || 0) + (s.eyeLookDownRight || 0)) / 2;
    }
    this.status = "tracked";
    this.message = "eyes tracked";
    this.lastSeen = now;
    this.frameId++;
  }

  reading() {
    if (this.ear == null || performance.now() - this.lastSeen > STALE_MS) return null;
    return { ear: this.ear, blink: this.blink, down: this.down };
  }
}

// Turns a LONG deliberate blink into one press. Normal blinks are ignored.
export class BlinkButton {
  constructor(calibration = load("calibration", null)) {
    this.closedTime = 0;
    this.openTime = 0;             // how long the eyes have been open again
    this.fired = false;
    this.baseline = null;          // this person's open-eye EAR, learned slowly
    this.calibration = calibration;
  }

  get threshold() {
    return this.baseline == null ? EAR_START : Math.max(0.08, 0.5 * this.baseline);
  }

  closed(r) {
    if (!r) return false;
    const c = this.calibration;
    const lookingDown = r.down != null && r.down > LOOK_DOWN;
    // the face model being very sure the eyes are shut always counts (unless looking down)
    if (!lookingDown && r.blink != null && r.blink > STRONG_BLINK) return true;
    if (c) {                                   // this person's measured cutoff
      if (c.signal === "blink" && r.blink != null) return r.blink > c.threshold;
      if (c.signal === "ear") return r.ear < c.threshold;
    }
    if (r.down != null && r.down > LOOK_DOWN) {
      // looking down makes the lids drop: demand a much deeper closure
      const base = this.baseline ?? 2 * EAR_START;
      return r.ear < Math.max(0.05, 0.28 * base);
    }
    // either sign counts: the eyelid gap is small, OR the face model itself is
    // confident the eyes are shut (helps with glasses, dim light, odd angles)
    return r.ear < this.threshold || (r.blink != null && r.blink > BLINK_SCORE);
  }

  learn(r) {
    if (!r || r.ear < this.threshold * 1.3) return;     // only clearly-open frames
    if (r.down != null && r.down > LOOK_DOWN) return;    // not while looking down
    this.baseline = this.baseline == null ? r.ear : this.baseline + 0.02 * (r.ear - this.baseline);
  }

  // Call every frame with the latest reading. Returns true once per long blink.
  update(r, dt) {
    this.learn(r);
    if (this.closed(r)) {
      this.openTime = 0;
      this.closedTime += dt;
      if (this.closedTime >= HOLD_SECONDS && !this.fired) {
        this.fired = true;
        return true;
      }
    } else {
      // one flickery "open" frame shouldn't restart a long blink
      this.openTime += dt;
      if (this.openTime >= OPEN_GRACE) {
        this.closedTime = 0;
        this.fired = false;
      }
    }
    return false;
  }
}

// ---------- calibration ----------
function pct(values, p) {
  const v = [...values].sort((a, b) => a - b);
  if (!v.length) return null;
  const k = ((v.length - 1) * p) / 100, lo = Math.floor(k), hi = Math.min(lo + 1, v.length - 1);
  return v[lo] + (v[hi] - v[lo]) * (k - lo);
}

// Pick the best way to tell CLOSED eyes from eyes LOOKING DOWN for this person.
// Each list holds {ear, blink} samples. EAR: closed is low. Blink score: closed
// is high. We compare the gap between "down" and "closed" (using the worst 10%
// of samples, to be safe) and use the signal with the bigger gap, with the
// cutoff in the middle of that gap.
export function computeCalibration(open, down, closed) {
  const E = (s) => s.map((x) => x.ear);
  const B = (s) => s.map((x) => x.blink).filter((x) => x != null);
  const res = { openEar: pct(E(open), 50), downEar: pct(E(down), 50), closedEar: pct(E(closed), 50) };
  const span = Math.max(1e-6, res.openEar - res.closedEar);
  let best = { signal: "ear", gap: (pct(E(down), 10) - pct(E(closed), 90)) / span,
               threshold: (pct(E(down), 10) + pct(E(closed), 90)) / 2 };
  if (B(open).length && B(down).length && B(closed).length) {
    const bspan = Math.max(1e-6, pct(B(closed), 50) - pct(B(open), 50));
    const gap = (pct(B(closed), 10) - pct(B(down), 90)) / bspan;
    if (gap > best.gap) best = { signal: "blink", gap, threshold: (pct(B(closed), 10) + pct(B(down), 90)) / 2 };
  }
  Object.assign(res, best, { ok: best.gap > 0 });
  if (!res.ok) {               // can't separate them: use the middle of the typical values
    res.signal = "ear";
    res.threshold = (res.downEar + res.closedEar) / 2;
  }
  res.made = new Date().toISOString();
  return res;
}
