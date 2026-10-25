# One-Button Talker: first prototype (desktop version)

This is where the project started: a Python app for a Mac or PC, controlled by the SPACE bar or a long
blink at the laptop's webcam. Everything we learned here went into the phone/tablet app in the main folder.

## Our eye-gaze experiments (why the app uses blinking)
Before building blink control we tested whether a normal webcam could tell **where** someone is looking.
We looked left, center and right and recorded the numbers (`gaze_test*.py`, `gaze_grid.py`):

| What we measured | Left | Center | Right | Verdict |
|---|---|---|---|---|
| Iris position (eyes only) | 0.54 | 0.51 | 0.42 | Too small and noisy to pick one of 26 letters |
| Head turn | 0.93 | 0.52 | 0.20 | Clear, but many patients can't turn their head |

**Blinking**, by contrast, was clear: the eye aspect ratio measured about **0.52 with eyes open** and
**0.06 closed**. So we built the app around a deliberate long blink. Later testing showed that **looking
down** lowered the eyelids enough to look like a blink, which led to the look-down check and the
calibration in both versions.

## Running it (Mac)
1. Double-click **Start Talker.command**. It installs pygame the first time.
2. Blink control turns on automatically if `mediapipe` and `opencv-python` are installed and the
   Terminal app is allowed to use the camera (System Settings → Privacy & Security → Camera).
   Without a camera, SPACE works on its own.


The face model (`face_landmarker.task`) downloads automatically the first time blink control starts.
Run the automated tests with `python3 tests.py`.

## Screens
- **HOME:** big tiles for KEYBOARD, NEEDS, FEELINGS, PAIN, PEOPLE, CHAT, YES / NO, SETTINGS and REST.
- **Phrase pages** (Needs, Feelings, Pain, People, Chat): each holds up to 15 ready-made phrases, spoken with one pick. Caregivers can rename or rewrite every page in `pages.txt`, for example adding CALL MAYA.
- **KEYBOARD:** spell anything, with word prediction.
- **SETTINGS:** speed, voice, talking scan, letter layout and help, all reachable with the one button. No keyboard or mouse needed.
- The urgent quick phrases (YES, NO, I NEED HELP, I AM IN PAIN, THANK YOU) are on every screen.

## Camera calibration (20 seconds)
Looking down lowers the eyelids, which a camera can mistake for a blink. Double-click
**Calibrate Camera.command** (with the app closed). A voice tells you to look at the screen, look down,
then close your eyes. It measures your eyes in each position and saves the best cutoff between
"looking down" and "closed" (`calibration.json`). Even without calibration, the app uses the face
model's "looking down" score to demand a deeper closure when your eyes are aimed down.

## Caregiver Companion (phone)
The laptop also runs a small private web page for a caregiver's phone. Press **C**, or go to
SETTINGS > CAREGIVER LINK, and scan the QR code with a phone on the same Wi-Fi. The phone shows:
- a live feed of everything the patient says, and red **help alerts** with an "I'm coming" button
- **ask a yes/no question:** it's read aloud on the patient's screen, and the answer comes back to the phone
- **send a message** that appears big on the patient's screen and is read aloud
- whether the patient is awake or resting, and when they last pressed

There's no account and no outside server; messages stay on the home network, and a secret key in the link
keeps others out. (The first time, macOS may ask to allow incoming connections. Click Allow.)

## Features
- **Quick phrases** (YES, NO, I NEED HELP...) spoken with one pick; caregivers can edit `quick_phrases.txt`
- **Help alarm:** I NEED HELP plays an alarm, flashes the screen red, and can push an alert to a caregiver's phone (`phone_alert.txt`, free ntfy app)
- **Pain follow-up:** after I AM IN PAIN, a row asks how bad and where it hurts
- **Word prediction** from 57,000 words, with patient words and 577 medicine names ranked first
- **Next-word prediction** (I → NEED → WATER) and **learning**: the user's own words, word pairs and sentences move to the top
- **Recent sentences:** sentences said before become one-pick buttons
- **SMART letter layout:** about 20% less waiting per letter than ABC order (see below)
- **Press counter:** shows how many presses a message took compared with spelling it out
- **Blink control** that ignores normal blinks, calibrates itself to each person and pauses scanning while the eyes are closed
- **REST mode**, **YES/NO screen**, **REPEAT**, adjustable speed, **talking scan** for low vision, voice choice, fullscreen
- Saved settings, a crash-safe camera (it falls back to SPACE if the camera fails), and automated tests

## The SMART layout math
With row-column scanning, reaching a letter takes (row number + column number) steps. We ranked
letters by how often they appear in English and put the most common letters in the spots with the
fewest steps. Weighted by letter frequency, the average is **4.54 steps per letter, compared with
5.64 for ABC order**, which is about 20% less waiting on every letter.

## Caregiver keys
SPACE select · H help · Y yes/no screen · A talking scan · V voice · L layout · F fullscreen · ESC quit

## Files
| File | What it is |
|---|---|
| `talker.py` | the app |
| `blink.py` | webcam blink detection (MediaPipe face landmarks, eye aspect ratio) |
| `words.txt` | word list: patient words, then English by frequency, plus medicines |
| `tests.py` | automated tests; run `python3 tests.py` |
| `pages.txt`, `quick_phrases.txt`, `phone_alert.txt` | caregiver settings (made on first run) |
| `care_server.py`, `caregiver.html` | Caregiver Companion: local web server + phone page |
| `calibrate.py` | 20-second guided camera calibration |
| `camera_worker.py` | runs the webcam in its own process (keeps the camera and the window apart) |
| `user_words.txt`, `user_pairs.txt`, `sentences.txt`, `settings.json` | what the app has learned, created automatically |
| `gaze_*.py`, `mp_solutions_shim.py` | our eye-gaze experiments (research, not used by the app) |

## AI use
We used an AI assistant (Claude) to help write parts of this code. See our submission for details.
