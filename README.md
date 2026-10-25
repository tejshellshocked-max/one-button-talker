# One-Button Talker

**Talk with one blink or one tap.** A free communication app for people who can't speak or move
(ALS, locked-in syndrome, stroke, spinal cord injury), and for the families and nurses who care for them.

**Open the app:** https://tejshellshocked-max.github.io/one-button-talker/
On an iPhone or iPad: tap Share, then **Add to Home Screen** to install it like a normal app.

## How it works
A highlight moves down the rows. When your row lights up, **tap anywhere** or **hold a blink for half a
second** in front of the front camera. Do it again when your item lights up. One movement is all it takes.

- **Home screen:** Keyboard, Needs, Feelings, Pain, People, Chat, Yes/No, Settings, Rest
- **Ready-made phrases**, each spoken with one pick ("I am thirsty", "Please move me", "My chest hurts")
- **Keyboard** with word prediction from 57,000 words, with patient words and medicine names first.
  It learns the user's own words, word pairs and sentences.
- **Help alarm:** a siren, a flashing red screen, and an alert on the caregiver's phone
- **I AM IN PAIN** jumps straight to the Pain page: a **0-10 pain scale** (the question every nurse asks;
  8 or higher also alerts the caregiver) plus where it hurts
- **Yes/No screen**, **Rest mode** (scanning stops until a long blink), **talking scan** for low vision
- **Settings work with the one button too:** speed, voice, camera, calibration, caregiver link

## Look to select (Apple Eye Tracking)
On iPhone 12 or newer (iOS 18+), turn on **Settings → Accessibility → Eye Tracking**, then start the app
with **Touch / Apple Eye Tracking** (or Settings → MODE). The moving highlight turns off and every tile
can be picked directly: **look at a tile and hold your gaze**, and iOS taps it. iPhones keep gaze data
private from apps and websites, so this works by turning the system's gaze-tap into a direct pick.

## Blink detection
Google's MediaPipe face model finds 478 points on the face every frame, **on the device; no video is
ever uploaded**. We measure the eye aspect ratio (eyelid gap ÷ eye width) plus the model's own "blink"
and "looking down" scores:
- A normal blink (~0.1 s) is ignored; a deliberate blink (0.35 s) is one press.
- Scanning pauses while the eyes are closed, so the highlight can't slide past your target.
- **Looking down lowers the eyelids**, so it can look like a blink. When the eyes are aimed down, the
  app demands a much deeper closure, and a 20-second **calibration** measures each person's own
  "looking down" and "closed" values and picks the best cutoff between them.

## SMART letter layout
With row-then-column scanning, reaching a letter takes (row + column) steps. We placed the most
common English letters in the spots with the fewest steps. Weighted by letter frequency, that's
**4.54 steps per letter instead of 5.64 for ABC order: about 20% less waiting**.

## Caregiver Companion
Settings → **Caregiver Link** shows a QR code. A caregiver scans it and gets a live feed of everything
said, help alerts with an "I'm coming" button, **yes/no questions** sent to the patient's screen
(the answer comes back), and messages shown on the patient's screen. It works anywhere, on Wi-Fi or
cellular. Messages are **end-to-end encrypted** (AES-GCM) in the browser: the key lives only in the
link's `#` part, which is never sent to a server. The relay (ntfy.sh) only sees scrambled data.

## Privacy and offline
Everything learned stays on the device. After the first visit the app works offline, including blink
detection.

## Files
| File | What it is |
|---|---|
| `index.html`, `style.css`, `app.js` | the patient app |
| `data.js` | phrases, pages, letter layouts, word prediction and learning |
| `eyes.js` | camera, face model, blink detection, calibration |
| `link.js` | encrypted caregiver link |
| `caregiver.html`, `caregiver.js` | the caregiver's phone page |
| `words.txt` | word list (patient words first, then English by frequency, plus medicines) |
| `sw.js`, `manifest.webmanifest`, `icons/` | installable app + offline support |
| `vendor/`, `models/` | MediaPipe Tasks Vision (Apache-2.0) and its face model; qrcode-generator (MIT) |

The first version was a Python desktop app (pygame + OpenCV); this web version brings it to phones and tablets.

## AI use
We used an AI assistant (Claude) to help write parts of this code. See our submission for details.
