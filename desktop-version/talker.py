"""
One-Button Talker (Congressional App Challenge 2026)

A typing-and-speaking app for people who can't speak or use a keyboard
(for example, people with ALS or paralysis) but can press ONE button.

How it works:
  - A highlight moves down the rows. Press the button (SPACE) when your row
    is lit, then press again when the item you want is lit.
  - Quick phrases (top row) are spoken instantly with one selection.
  - Suggested words appear as you type, most useful words first.
  - SPEAK reads the sentence out loud. SLOWER / FASTER change scan speed.

Run:  double-click "Start Talker.command"  (or: python3 talker.py)

AI assistance (Claude) was used to write parts of this code; see README.
"""
import os
import json
import random
import string
import subprocess
import threading
import time
import urllib.request
import pygame

# ---------- settings ----------
START_SCAN_SECONDS = 1.0     # how long the highlight stays on each option
MIN_SCAN, MAX_SCAN = 0.5, 3.0
SWITCH_KEY = pygame.K_SPACE  # the "one button"
WIDTH, HEIGHT = 1000, 770

QUICK_PHRASES = ["YES", "NO", "I NEED HELP", "I AM IN PAIN", "THANK YOU"]
# A caregiver can edit quick_phrases.txt (one phrase per line, up to 6)
# to put this person's most-needed phrases on the top row.
_QP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quick_phrases.txt")
try:
    with open(_QP_FILE) as _f:
        _custom = [ln.strip().upper() for ln in _f if ln.strip() and not ln.startswith("#")]
    if _custom:
        QUICK_PHRASES = _custom[:6]
except FileNotFoundError:
    pass
def is_alert(phrase):
    """Phrases with the word HELP sound the alarm (e.g. 'I NEED HELP', 'HELP ME'),
    and so do a few other emergencies (see URGENT_PHRASES)."""
    return "HELP" in phrase.split() or phrase in URGENT_PHRASES


PAIN_PHRASES = {"I AM IN PAIN", "I'M IN PAIN", "PAIN", "IT HURTS", "I HURT"}
# Two letter layouts. "smart" puts the most-used letters where the highlight
# reaches them soonest (top-left). Steps to reach a letter = row + column, so
# we sorted letters by how common they are in English and filled the spots
# with the fewest steps first. Average: 4.54 steps per letter vs 5.64 for
# ABC order = about 20% less waiting. Press L to switch layouts.
LAYOUTS = {
    "smart": [list("ETOSLW"), list("AIHCFP"), list("NRUGBK"), list("DMYVJXQZ")],
    "abc":   [list("ABCDEF"), list("GHIJKL"), list("MNOPQR"), list("STUVWXYZ")],
}
LETTER_ROWS = LAYOUTS["abc"]
CONTROL_ROW = ["SPACE", "DEL", "SPEAK", "REPEAT", "CLEAR", "REST", "HOME"]
YESNO_ITEMS = ["YES", "NO", "BACK"]

# ---------- pages ----------
# The app opens on a HOME screen of big category tiles. Each category is a
# page of ready-made phrases (one pick = spoken). KEYBOARD is for anything else.
# Caregivers can change every page in pages.txt (made on first run).
DEFAULT_PAGES = [
    ("NEEDS", ["I AM THIRSTY", "I AM HUNGRY", "I NEED THE BATHROOM",
               "I AM COLD", "I AM HOT", "PLEASE MOVE ME",
               "I WANT TO SLEEP", "TURN THE LIGHT OFF", "TURN THE TV ON",
               "I NEED MY MEDICINE", "PLEASE SUCTION ME", "I NEED MY GLASSES"]),
    ("FEELINGS", ["I AM OKAY", "I AM HAPPY", "I AM SAD",
                  "I AM SCARED", "I AM TIRED", "I AM BORED",
                  "I AM FRUSTRATED", "I FEEL BETTER", "I FEEL WORSE"]),
    ("PAIN", ["MY HEAD HURTS", "MY CHEST HURTS", "MY STOMACH HURTS",
              "MY BACK HURTS", "MY LEGS HURT", "MY ARMS HURT",
              "IT HURTS A LITTLE", "IT HURTS A LOT", "THE PAIN IS VERY BAD",
              "I FEEL SICK", "I FEEL DIZZY", "I CAN'T BREATHE WELL"]),
    ("PEOPLE", ["CALL THE NURSE", "CALL THE DOCTOR", "CALL MY FAMILY",
                "CALL MY MOM", "CALL MY DAD", "CALL MY FRIEND",
                "I WANT TO BE ALONE", "PLEASE STAY WITH ME", "WHEN ARE THEY COMING?"]),
    ("CHAT", ["HELLO", "GOODBYE", "HOW ARE YOU?",
              "I AM GOOD", "THANK YOU", "I LOVE YOU",
              "PLEASE WAIT", "I DON'T KNOW", "PLEASE SAY THAT AGAIN",
              "WHAT TIME IS IT?", "PLEASE TALK TO ME", "THAT'S FUNNY"]),
]
# phrases that also sound the alarm (besides anything with the word HELP)
URGENT_PHRASES = {"THE PAIN IS VERY BAD", "I CAN'T BREATHE WELL", "MY CHEST HURTS"}
MAX_PAGES, MAX_PHRASES = 6, 15
NAV_ITEMS = ["KEYBOARD", "YES / NO", "SETTINGS", "REST"]
TILE_COLORS = {"KEYBOARD": (205, 225, 255), "NEEDS": (200, 235, 205), "FEELINGS": (255, 228, 190),
               "PAIN": (255, 205, 205), "PEOPLE": (225, 215, 250), "CHAT": (200, 235, 235),
               "YES / NO": (235, 235, 200), "SETTINGS": (225, 225, 225), "REST": (210, 210, 225)}

HELP_LINES = [
    ("SPACE", "the one button (or hold a long blink)"),
    ("H", "show / hide this help"),
    ("Y", "big YES / NO screen   (HOME screen has it too)"),
    ("A", "talking scan on / off (reads each row out loud)"),
    ("V", "change voice"),
    ("L", "letter layout: SMART or ABC"),
    ("C", "caregiver link for a phone (also in SETTINGS)"),
    ("F", "fullscreen"),
    ("ESC", "quit"),
    ("", ""),
    ("Files", "pages.txt = phrase pages (NEEDS, PAIN...) - edit freely"),
    ("", "quick_phrases.txt = top-row phrases (one per line)"),
    ("", "phone_alert.txt = ntfy topic for phone alerts"),
]
WAKE_SECONDS = 1.5   # while resting, hold a blink this long to wake up

WHITE = (255, 255, 255)
BLACK = (25, 25, 25)
GRAY = (215, 215, 215)
DIM = (150, 150, 150)
HIGHLIGHT = (255, 205, 60)
SUGGEST = (205, 225, 255)
QUICK = (200, 235, 205)
CONTROL = (230, 220, 245)

HISTORY = (255, 230, 200)
PAIN = (255, 210, 210)
ALARM_RED = (230, 40, 40)

ROW_COLORS = {"quick": QUICK, "suggest": SUGGEST, "letters": GRAY, "control": CONTROL,
              "history": HISTORY, "pain": PAIN}

# After "I AM IN PAIN", a follow-up row asks how bad and where.
PAIN_ROW = ["A LITTLE", "A LOT", "VERY BAD", "HEAD", "CHEST", "STOMACH", "BACK", "LEGS"]
PAIN_SAY = {"A LITTLE": "It hurts a little.", "A LOT": "It hurts a lot.",
            "VERY BAD": "The pain is very bad. Please help me now."}

_HERE = os.path.dirname(os.path.abspath(__file__))

_PAGES_FILE = os.path.join(_HERE, "pages.txt")


def load_pages():
    """Read pages.txt:  [PAGE NAME] on its own line, then one phrase per line."""
    pages, current = [], None
    try:
        with open(_PAGES_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    name = line[1:-1].strip().upper()
                    if name and name not in NAV_ITEMS and name != "HOME":
                        current = (name, [])
                        pages.append(current)
                    else:
                        current = None
                elif current is not None and len(current[1]) < MAX_PHRASES:
                    current[1].append(line.upper())
    except OSError:
        return list(DEFAULT_PAGES)
    pages = [p for p in pages if p[1]][:MAX_PAGES]
    return pages or list(DEFAULT_PAGES)


def make_pages_file():
    """First run: write the default pages so a caregiver can edit them."""
    if os.path.exists(_PAGES_FILE):
        return
    try:
        with open(_PAGES_FILE, "w") as f:
            f.write("# One-Button Talker phrase pages - edit freely, then restart the app.\n"
                    "# [PAGE NAME] starts a page (up to 6 pages), then one phrase per line\n"
                    "# (up to 15). Put a real name in, e.g. CALL MAYA.\n\n")
            for name, phrases in DEFAULT_PAGES:
                f.write(f"[{name}]\n" + "\n".join(phrases) + "\n\n")
    except OSError:
        pass


def chunks(items, n=3):
    return [items[i:i + n] for i in range(0, len(items), n)]


# ---------- saved settings (speed, talking scan) ----------
_SETTINGS_FILE = os.path.join(_HERE, "settings.json")


def load_settings():
    try:
        with open(_SETTINGS_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(**changes):
    data = load_settings()
    data.update(changes)
    try:
        with open(_SETTINGS_FILE, "w") as f:
            json.dump(data, f)
    except OSError:
        pass


# ---------- sentence history ----------
# Every sentence the user SPEAKs is saved, so the ones they say often
# ("I WANT TO GO TO BED") become one-pick buttons instead of re-spelling.
_HISTORY_FILE = os.path.join(_HERE, "sentences.txt")
SENTENCES = {}          # sentence -> times said
try:
    with open(_HISTORY_FILE) as f:
        for line in f:
            count, _, sent = line.rstrip("\n").partition("\t")
            if sent:
                SENTENCES[sent] = int(count)
except (FileNotFoundError, ValueError):
    pass


def remember_sentence(text):
    text = " ".join(text.upper().split())
    if len(text.split()) < 2:          # single words aren't worth a button
        return
    SENTENCES[text] = SENTENCES.get(text, 0) + 1
    # move it to the end so recent ones win ties
    SENTENCES[text] = SENTENCES.pop(text)
    LEARNED[0] += 1
    try:
        with open(_HISTORY_FILE, "w") as f:
            for sent, c in SENTENCES.items():
                f.write(f"{c}\t{sent}\n")
    except OSError:
        pass


def top_sentences(n=3):
    order = list(SENTENCES)
    ranked = sorted(order, key=lambda s: (-SENTENCES[s], -order.index(s)))
    return ranked[:n]


# ---------- word prediction ----------
# Load the word list ONCE when the program starts (not on every keypress).
# words.txt has one word per line: patient-need words first, then the most
# common English words in order of how often they're used.
_WORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "words.txt")
try:
    with open(_WORDS_FILE) as f:
        WORDS = [w.strip().upper() for w in f if w.strip()]
except FileNotFoundError:
    WORDS = ["HELLO", "HELP", "YES", "NO", "PLEASE", "THANK", "WATER"]
WORD_SET = set(WORDS)

# Goes up every time the app learns something, so cached suggestions refresh.
LEARNED = [0]


# Words THIS user has picked before, with how many times. Saved to a file so
# the app learns their vocabulary over time (e.g. a family member's name).
_USER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_words.txt")
USER_COUNTS = {}
try:
    with open(_USER_FILE) as f:
        for line in f:
            word, _, count = line.strip().partition(" ")
            if word:
                USER_COUNTS[word] = int(count) if count.isdigit() else 1
except FileNotFoundError:
    pass


def remember_word(word):
    """Count a word the user finished, and save the counts."""
    word = word.strip().upper()
    if len(word) < 2 or not word.isalpha():
        return
    USER_COUNTS[word] = USER_COUNTS.get(word, 0) + 1
    LEARNED[0] += 1
    try:
        with open(_USER_FILE, "w") as f:
            for w, c in sorted(USER_COUNTS.items(), key=lambda x: -x[1]):
                f.write(f"{w} {c}\n")
    except OSError:
        pass


def trusted(word):
    """A learned word is suggested if it's a real word, or a new word
    (like a name) the user has typed at least twice - so one typo
    doesn't keep popping up as a suggestion."""
    return word in WORD_SET or USER_COUNTS.get(word, 0) >= 2


def predict_words(prefix, n=3):
    """Return up to n words that start with `prefix`.

    Words this user picks often come first, then the word list
    (patient-need words, then English words by how common they are).
    """
    if not prefix:
        return []
    matches = []
    personal = sorted((w for w in USER_COUNTS
                       if w.startswith(prefix) and w != prefix and trusted(w)),
                      key=lambda w: -USER_COUNTS[w])
    for w in personal + WORDS:
        if w.startswith(prefix) and w != prefix and w not in matches:
            matches.append(w)
            if len(matches) == n:
                break
    return matches


# ---------- next-word prediction ----------
# After a finished word, suggest likely NEXT words (no letters typed yet).
NEXT_WORDS = {
    "": ["I", "PLEASE", "CAN"],
    "I": ["NEED", "WANT", "AM", "FEEL", "LOVE"],
    "NEED": ["WATER", "HELP", "BATHROOM", "NURSE", "MEDICINE", "REST"],
    "WANT": ["WATER", "TO", "MY", "MORE"],
    "AM": ["IN", "COLD", "HOT", "TIRED", "HUNGRY", "THIRSTY", "OKAY"],
    "FEEL": ["SICK", "DIZZY", "BETTER", "WORSE", "TIRED", "PAIN"],
    "IN": ["PAIN", "BED"],
    "MY": ["HEAD", "STOMACH", "BACK", "CHEST", "LEGS", "FAMILY"],
    "PLEASE": ["HELP", "CALL", "TURN", "MOVE", "STOP"],
    "CALL": ["MY", "NURSE", "DOCTOR", "MOM", "DAD"],
    "CAN": ["YOU", "I"],
    "YOU": ["PLEASE", "HELP"],
    "TURN": ["ME", "OFF", "ON"],
    "THANK": ["YOU"],
    "LOVE": ["YOU"],
    "TO": ["SLEEP", "SIT", "EAT", "DRINK", "GO", "TALK"],
    "PAIN": ["IS"],
    "IS": ["SHARP", "BAD", "WORSE", "BETTER"],
}

# Word pairs this user has typed (e.g. "CALL MAYA"), learned over time.
_PAIRS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_pairs.txt")
USER_PAIRS = {}
try:
    with open(_PAIRS_FILE) as f:
        for line in f:
            p = line.split()
            if len(p) >= 2:
                USER_PAIRS.setdefault(p[0], {})[p[1]] = (int(p[2]) if len(p) > 2
                                                         and p[2].isdigit() else 1)
except FileNotFoundError:
    pass


def remember_pair(prev, word):
    prev, word = prev.strip().upper(), word.strip().upper()
    if not prev.isalpha() or not word.isalpha():
        return
    d = USER_PAIRS.setdefault(prev, {})
    d[word] = d.get(word, 0) + 1
    LEARNED[0] += 1
    try:
        with open(_PAIRS_FILE, "w") as f:
            for a, nexts in USER_PAIRS.items():
                for b, c in nexts.items():
                    f.write(f"{a} {b} {c}\n")
    except OSError:
        pass


def predict_next(prev, n=3):
    """Likely next words after `prev` (learned pairs first, then built-in)."""
    prev = prev.upper()
    learned = sorted((w for w in USER_PAIRS.get(prev, {}) if trusted(w)),
                     key=lambda w: -USER_PAIRS[prev][w])
    out = []
    for w in learned + NEXT_WORDS.get(prev, []):
        if w not in out:
            out.append(w)
    return out[:n]


# ---------- sounds ----------
def click_sound():
    """Short tick so the user knows a selection happened."""
    try:
        subprocess.Popen(["afplay", "-v", "0.4", "/System/Library/Sounds/Tink.aiff"])
    except FileNotFoundError:
        pass


# ---------- text-to-speech (Mac built-in voice) ----------
def alert_then_speak(text):
    """Play a loud alert sound 3 times, then say the text (Mac).

    A quiet voice can be missed from another room; the alarm gets
    a caregiver's attention first.
    """
    sound = "/System/Library/Sounds/Sosumi.aiff"
    phone_alert(text)

    def run():
        # run each command directly (no shell), so text like "I'M COLD"
        # with an apostrophe can't break the command
        try:
            for _ in range(3):
                subprocess.run(["afplay", sound])
            subprocess.run(["say"] + voice_args() + [text])
        except FileNotFoundError:          # not on a Mac
            print("ALERT:", text)
    threading.Thread(target=run, daemon=True).start()


def speak(text):
    """Say `text` out loud using the Mac's built-in `say` command.

    Popen (not run) so the app keeps scanning while it talks.
    On Windows, swap this for pyttsx3.
    """
    if text.strip():
        try:
            return subprocess.Popen(["say"] + voice_args() + [text])
        except FileNotFoundError:          # not on a Mac
            print("SPEAK:", text)
    return None


# ---------- phone alert for caregivers ----------
# If phone_alert.txt holds a topic name, "I NEED HELP" also sends a push
# notification to every phone subscribed to that topic in the free ntfy app.
_PHONE_FILE = os.path.join(_HERE, "phone_alert.txt")


def phone_topic():
    try:
        with open(_PHONE_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except FileNotFoundError:
        pass
    return None


def make_phone_file():
    """First run: create phone_alert.txt with a random private topic name."""
    if os.path.exists(_PHONE_FILE):
        return
    topic = "talker-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    try:
        with open(_PHONE_FILE, "w") as f:
            f.write("# Phone alerts: install the free 'ntfy' app on a caregiver's phone,\n"
                    "# tap +, and subscribe to the topic name below. Delete this file to\n"
                    "# turn phone alerts off.\n" + topic + "\n")
    except OSError:
        pass


def phone_alert(text):
    """Send `text` to the caregiver's phone without freezing the app."""
    topic = phone_topic()
    if not topic:
        return

    def send():
        # The Mac's own `curl` uses the Mac's security certificates, so this
        # works with any Python (python.org's Python can't verify HTTPS
        # out of the box, which made urllib fail).
        try:
            r = subprocess.run(
                ["curl", "-s", "-m", "8", "-H", "Title: One-Button Talker",
                 "-H", "Priority: urgent", "-H", "Tags: rotating_light",
                 "-d", text, "https://ntfy.sh/" + topic],
                capture_output=True)
            if r.returncode != 0:
                raise OSError(f"curl error {r.returncode}")
        except Exception:
            try:                          # no curl: try Python's own way
                req = urllib.request.Request(
                    "https://ntfy.sh/" + topic, data=text.encode("utf-8"),
                    headers={"Title": "One-Button Talker", "Priority": "urgent",
                             "Tags": "rotating_light"})
                urllib.request.urlopen(req, timeout=8)
            except Exception as e:        # no internet: the sound alarm still works
                print("Phone alert not sent:", e)
    threading.Thread(target=send, daemon=True).start()


# ---------- voices ----------
def list_voices():
    """English voices installed on this Mac (first entry = system default)."""
    voices = [None]
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith("en_") and "(" not in parts[0]:
                voices.append(parts[0])
    except Exception:
        pass
    return voices


CURRENT_VOICE = [None]      # changed with the V key


def voice_args():
    return ["-v", CURRENT_VOICE[0]] if CURRENT_VOICE[0] else []


ROW_NAMES = {"quick": "phrases", "suggest": "words", "control": "controls",
             "history": "recent", "pain": "pain"}


def row_name(kind, items):
    """What the talking scan says for a whole row."""
    if kind == "letters":
        return f"{items[0]} to {items[-1]}"
    if kind in ("menu", "nav", "setting"):
        return ", ".join(items)
    if kind == "phrase":
        return items[0]
    return ROW_NAMES.get(kind, kind)


def draw_link_screen(talker, screen, font, big_font, small_font):
    """Big screen with the caregiver link (and a QR code if available)."""
    W, H = screen.get_size()
    shade = pygame.Surface((W, H), pygame.SRCALPHA)
    shade.fill((20, 20, 30, 245))
    screen.blit(shade, (0, 0))
    title = big_font.render("Caregiver link", True, WHITE)
    screen.blit(title, title.get_rect(midtop=(W // 2, 30)))
    if not talker.care:
        msg = font.render("The caregiver link is off.", True, WHITE)
        screen.blit(msg, msg.get_rect(center=(W // 2, H // 2)))
        return
    url = talker.care.url()
    y = 30 + title.get_height() + 20
    matrix = qr_matrix(url)
    if matrix:
        size = min(W - 80, H - y - 190)
        cell = max(2, size // (len(matrix) + 8))
        side = cell * (len(matrix) + 8)
        x0 = W // 2 - side // 2
        pygame.draw.rect(screen, WHITE, (x0, y, side, side), border_radius=8)
        for r, row in enumerate(matrix):
            for c, on in enumerate(row):
                if on:
                    pygame.draw.rect(screen, BLACK, (x0 + (c + 4) * cell, y + (r + 4) * cell, cell, cell))
        y += side + 20
    lines = ["Scan with a phone on the same Wi-Fi, or open:", url,
             "See what they say, get help alerts, ask yes/no questions."]
    for i, text in enumerate(lines):
        f = big_font if i == 1 and big_font.size(text)[0] < W - 60 else font
        surf = f.render(text, True, HIGHLIGHT if i == 1 else WHITE)
        screen.blit(surf, surf.get_rect(midtop=(W // 2, y)))
        y += surf.get_height() + 10
    tip = small_font.render("Press to close.", True, GRAY)
    screen.blit(tip, tip.get_rect(midtop=(W // 2, H - 40)))


def qr_matrix(text):
    """QR code as rows of True/False, if the small 'qrcode' library is installed."""
    try:
        import qrcode
        q = qrcode.QRCode(border=0)
        q.add_data(text)
        q.make(fit=True)
        return q.get_matrix()
    except Exception:
        return None


def fit_label(label, rect, fonts, color):
    """Render a tile label so it fits: one line, else two lines, trying
    each font from biggest to smallest, else cut it short with '...'."""
    max_w, max_h = rect.width - 12, rect.height - 6
    words = label.split()
    for f in fonts:
        one = f.render(label, True, color)
        if one.get_width() <= max_w and one.get_height() <= max_h:
            return [one]
        if len(words) > 1:
            best = None
            for cut in range(1, len(words)):
                a, b = " ".join(words[:cut]), " ".join(words[cut:])
                wid = max(f.size(a)[0], f.size(b)[0])
                if best is None or wid < best[0]:
                    best = (wid, a, b)
            if best[0] <= max_w and 2 * f.get_linesize() <= max_h:
                return [f.render(best[1], True, color), f.render(best[2], True, color)]
    f = fonts[-1]
    cut = label
    surf = f.render(cut, True, color)
    while surf.get_width() > max_w and len(cut) > 4:
        cut = cut[:-1]
        surf = f.render(cut.rstrip() + "...", True, color)
    return [surf]


class Talker:
    def __init__(self):
        self.text = ""
        self.mode = "row"      # "row" = scanning rows, "item" = scanning inside one row
        self.index = 0
        self.row = None        # (kind, items) picked while in "item" mode
        self.timer = 0.0
        self.scan_seconds = START_SCAN_SECONDS
        self.status = "Press SPACE or do a long blink when your row lights up.   (H = help)"
        self.paused = False    # scanning pauses while the eye is closed
        self.loops = 0         # times the highlight has gone around a row
        self.blink_progress = 0.0   # 0..1 while a long blink is being held
        self.face_seen = None       # True/False when the camera is on
        self.camera_label = ""      # camera status shown bottom-right
        self.last_spoken = ""       # for REPEAT
        self.resting = False        # REST mode: scanning stops until woken
        settings = load_settings()
        try:
            speed = float(settings.get("scan_seconds", START_SCAN_SECONDS))
        except (TypeError, ValueError):
            speed = START_SCAN_SECONDS
        self.scan_seconds = min(MAX_SCAN, max(MIN_SCAN, speed))
        self.audio_scan = bool(settings.get("audio_scan", False))
        self.show_pain = False      # pain follow-up row is showing
        self.alarm_until = 0        # screen flashes red until this time (ms)
        self.speech = None          # the `say` process for real speech
        self.voice = None           # the `say` process for the talking scan
        self.layout = settings.get("layout", "smart")
        if self.layout not in LAYOUTS:
            self.layout = "smart"
        self.yesno = False          # big YES / NO screen
        self.pages = load_pages()   # phrase pages (NEEDS, FEELINGS, ...)
        self.page = "HOME"          # HOME, KEYBOARD, SETTINGS, or a phrase page name
        self.show_help = False      # caregiver help screen (H key)
        self.care = None            # caregiver companion link (care_server.CareLink)
        self.question = None        # yes/no question from the caregiver's phone
        self.banner = None          # message from the caregiver's phone
        self.banner_until = 0
        self.show_link = False      # big caregiver-link screen (C key / settings)
        self.presses = 0            # presses used for the current message
        self.voices = None          # filled the first time V is pressed
        v = settings.get("voice")
        # ignore a saved voice that isn't text or isn't installed on this Mac
        # (otherwise `say` would fail and NOTHING would be spoken)
        if not isinstance(v, str) or v not in list_voices():
            v = None
        CURRENT_VOICE[0] = v

    # The rows on screen right now, as (kind, items).
    # A suggestion row appears only while a word is being typed.
    def rows(self):
        # rows() is called many times per frame; only recompute when
        # something changed (typing 1 letter used to re-search 57,000 words
        # several times a frame)
        key = (self.page, self.text, self.show_pain, self.layout, LEARNED[0],
               self.audio_scan, self.scan_seconds, CURRENT_VOICE[0])
        if getattr(self, "_rows_key", None) != key:
            self._rows_key = key
            self._rows = self._build_rows()
        return self._rows

    def page_names(self):
        return [name for name, _ in self.pages]

    def _build_rows(self):
        quick = [("quick", QUICK_PHRASES)]    # urgent phrases on every page
        if self.page == "HOME":
            tiles = ["KEYBOARD"] + self.page_names() + ["YES / NO", "SETTINGS", "REST"]
            return quick + [("menu", r) for r in chunks(tiles, 3)]
        if self.page == "SETTINGS":
            voice = CURRENT_VOICE[0] or "DEFAULT"
            return quick + [
                ("setting", ["SLOWER", "FASTER"]),
                ("setting", [f"VOICE: {voice.upper()}",
                             "TALKING SCAN: " + ("ON" if self.audio_scan else "OFF")]),
                ("setting", ["LETTERS: " + self.layout.upper(), "HELP SCREEN"]),
                ("setting", ["CAREGIVER LINK"]),
                ("nav", ["HOME"]),
            ]
        if self.page in self.page_names():
            phrases = dict(self.pages)[self.page]
            return (quick + [("phrase", r) for r in chunks(phrases, 3)]
                    + [("nav", ["HOME", "KEYBOARD"])])
        return self._keyboard_rows()

    def _keyboard_rows(self):
        rows = [("quick", QUICK_PHRASES)]
        if self.show_pain:
            rows.append(("pain", PAIN_ROW))
        if not self.text.strip() and SENTENCES:
            rows.append(("history", top_sentences()))
        words = self.text.split(" ")
        if words[-1]:
            suggestions = predict_words(words[-1])
        else:
            prev = words[-2] if len(words) >= 2 else ""
            suggestions = predict_next(prev)
        if suggestions:
            rows.append(("suggest", suggestions))
        rows += [("letters", r) for r in LAYOUTS[self.layout]]
        rows.append(("control", CONTROL_ROW))
        return rows

    # What the highlight is moving across right now
    def options(self):
        if self.yesno:
            return YESNO_ITEMS
        if self.mode == "row":
            return self.rows()
        return self.row[1] + ["BACK"]

    def update(self, dt):
        if self.paused or self.resting or self.show_help or self.show_link:   # hold still
            return
        self.timer += dt
        # the first item waits 1.5x longer, giving time to react after a pick
        wait = self.scan_seconds * (1.5 if self.index == 0 else 1.0)
        if self.timer >= wait:
            self.timer = 0.0
            self.index = (self.index + 1) % len(self.options())
            if self.index == 0:
                self.loops += 1
                # nothing picked after 2 trips through a row: go back to rows
                if self.mode == "item" and self.loops >= 2 and not self.yesno:
                    self.mode = "row"
                    self.index = 0
                    self.loops = 0
                    self.status = "No pick - back to all rows."
                # pain row goes away if it's ignored for 2 full loops
                if self.mode == "row" and self.show_pain and self.loops >= 2:
                    self.show_pain = False
                    self.loops = 0
            self.announce()

    def announce(self):
        """Talking scan: say what is lit, for users who can't see the screen well."""
        if not self.audio_scan:
            return
        if self.speech and self.speech.poll() is None:   # don't talk over real speech
            return
        if pygame.time.get_ticks() < self.alarm_until + 4000:   # or over the alarm
            return
        opts = self.options()
        if self.index >= len(opts):
            return
        item = opts[self.index]
        label = row_name(*item) if (self.mode == "row" and not self.yesno) else item
        if self.voice and self.voice.poll() is None:
            self.voice.terminate()
        try:
            self.voice = subprocess.Popen(["say", "-r", "230", label.lower()])
        except FileNotFoundError:
            pass

    def say(self, text, report=True):
        if self.voice and self.voice.poll() is None:
            self.voice.terminate()
        self.speech = speak(text)
        if report and text.strip():
            self.report("said", text)

    def alarm(self, text):
        """Emergency: alarm sound + speech + phone alert + red flashing screen."""
        alert_then_speak(text)
        self.alarm_until = pygame.time.get_ticks() + 5000
        self.report("alert", text)

    # ---------- caregiver companion (care_server.py) ----------
    def report(self, kind, text):
        if self.care:
            self.care.add(kind, text)

    def poll_care(self):
        """Called every frame: bring in questions/messages from the caregiver's phone."""
        if not self.care:
            return
        self.care.set_status(page=self.page, resting=self.resting)
        q = self.care.pop_question()
        if q:
            self.resting = False            # a caregiver question wakes the screen
            self.show_help = False
            self.question = q
            self.yesno = True
            self.mode = "row"
            self.index, self.timer, self.loops = 0, 0.0, 0
            self.say("Question. " + q, report=False)
            self.status = "Caregiver question - answer YES or NO."
        m = self.care.pop_message()
        if m:
            self.banner = m
            self.banner_until = pygame.time.get_ticks() + 12000
            self.say("Message. " + m, report=False)

    def toggle_layout(self):
        self.layout = "abc" if self.layout == "smart" else "smart"
        save_settings(layout=self.layout)
        self.mode, self.index, self.timer = "row", 0, 0.0
        self.status = ("Letter layout: SMART (most-used letters first)." if self.layout == "smart"
                       else "Letter layout: ABC order.")

    def next_voice(self):
        if self.voices is None:
            self.voices = list_voices()
        i = self.voices.index(CURRENT_VOICE[0]) if CURRENT_VOICE[0] in self.voices else 0
        CURRENT_VOICE[0] = self.voices[(i + 1) % len(self.voices)]
        save_settings(voice=CURRENT_VOICE[0])
        name = CURRENT_VOICE[0] or "default"
        self.status = f"Voice: {name}  ({len(self.voices) - 1} voices - pick VOICE again for the next)"
        self.say("Hello, this is my voice.", report=False)

    def message_done(self, text):
        """After SPEAK: show how many presses the message took vs spelling it."""
        letters = len(text.strip())
        spelled = 2 * letters + 2          # 2 presses per letter/space, +2 for SPEAK
        if self.presses and letters:
            saved = max(0, round(100 * (spelled - self.presses) / spelled))
            self.status = (f"Said in {self.presses} presses (spelling letter by letter: "
                           f"{spelled}) - {saved}% fewer.")
        self.presses = 0

    def toggle_audio_scan(self):
        self.audio_scan = not self.audio_scan
        save_settings(audio_scan=self.audio_scan)
        self.status = "Talking scan ON." if self.audio_scan else "Talking scan OFF."

    def press(self):
        """Called when the one button is pressed."""
        if self.care:
            self.care.set_status(last_press=time.time())
        if self.show_help or self.show_link:   # a press just closes the overlay
            self.show_help = self.show_link = False
            return
        if self.resting:
            self.wake()
            return
        if self.yesno:
            choice = YESNO_ITEMS[self.index]
            click_sound()
            if choice == "BACK":
                if self.question:
                    self.report("answer", f"(closed without answering) {self.question}")
                    self.question = None
                self.yesno = False
                self.mode, self.status = "row", "Back."
            elif self.question:
                # answer to a caregiver's question: say it, send it to their
                # phone, and go back to where the patient was
                self.say(choice, report=False)
                self.report("answer", f"{choice} - {self.question}")
                self.last_spoken = choice
                self.status = f'Answered {choice}: "{self.question}"'
                self.question = None
                self.yesno = False
                self.mode = "row"
            else:
                self.say(choice)
                self.last_spoken = choice
                self.status = f'Said: "{choice.capitalize()}"'
            self.index, self.timer, self.loops = 0, 0.0, 0
            self.announce()
            return
        self.presses += 1
        opts = self.options()
        self.index %= len(opts)
        choice = opts[self.index]
        if self.mode == "row":
            self.row = choice
            self.mode = "item"
            self.index = 0
        else:
            kind = self.row[0]
            if not (kind == "quick" or choice in ("SPEAK",)):
                click_sound()
            self.choose(kind, choice)
            self.mode = "row"
            self.index = self.restart_row(kind, choice)
        self.timer = 0.0
        self.loops = 0
        if self.index >= len(self.options()):
            self.index = 0
        self.announce()

    def go_page(self, name):
        self.page = name
        self.mode, self.index, self.timer, self.loops = "row", 0, 0.0, 0
        self.show_pain = False
        self.status = {"HOME": "Home - pick a page.", "KEYBOARD": "Keyboard - spell anything.",
                       "SETTINGS": "Settings - changes are saved."}.get(name, f"{name.capitalize()} - pick a phrase.")

    def wake(self):
        self.resting = False
        self.mode, self.index, self.timer, self.loops = "row", 0, 0.0, 0
        self.status = "Awake - scanning again."

    def restart_row(self, kind, item):
        """Where the highlight starts after a pick.

        While typing, skip the quick-phrase row and start at the suggestions
        (or the first letter row) - that's almost always what comes next.
        """
        if self.page != "KEYBOARD":
            # on a phrase page, start on the phrases (row 1), not the quick row
            if kind == "phrase":
                return 1
            jump, self.jump_to = getattr(self, "jump_to", None), None
            return jump if jump is not None else 0
        kinds = [k for k, _ in self.rows()]
        if self.show_pain:                 # just said "I am in pain": ask more
            return kinds.index("pain")
        typing = kind in ("letters", "suggest") or item in ("SPACE", "DEL")
        if not typing:
            return 0
        return kinds.index("suggest") if "suggest" in kinds else kinds.index("letters")

    def choose(self, kind, item):
        if item == "BACK":
            return
        if kind != "pain":
            self.show_pain = False
        if kind in ("quick", "pain", "history") and not self.text.strip():
            self.presses = 0
        if kind == "quick":                       # urgent phrases: speak right away
            if is_alert(item):
                self.alarm(item)
            else:
                self.say(item)
            self.last_spoken = item
            self.status = f'Said: "{item.capitalize()}"'
            if item in PAIN_PHRASES:
                if self.page == "KEYBOARD" or "PAIN" not in self.page_names():
                    self.show_pain = True
                    self.status += "  - pick how bad, or where it hurts."
                elif self.page != "PAIN":
                    self.go_page("PAIN")
                    self.jump_to = 1            # start on the pain phrases
                    self.status = 'Said: "I am in pain" - where does it hurt?'
        elif kind == "menu":
            if item == "YES / NO":
                self.yesno = True
                self.index = 0
                self.status = "Yes / No - pick BACK to leave."
            elif item == "REST":
                self.resting = True
                self.status = "Resting. Hold a blink 1.5 s (or press SPACE) to wake."
            else:
                self.go_page(item)
                if item in self.page_names():
                    self.jump_to = 1        # start on the phrases, not the quick row
        elif kind == "phrase":
            if is_alert(item):
                self.alarm(item)
            else:
                self.say(item)
            self.last_spoken = item
            self.status = f'Said: "{item.capitalize()}"'
        elif kind == "nav":
            self.go_page(item)
        elif kind == "setting":
            if item in ("SLOWER", "FASTER"):
                step = 0.25 if item == "SLOWER" else -0.25
                self.scan_seconds = min(MAX_SCAN, max(MIN_SCAN, self.scan_seconds + step))
                save_settings(scan_seconds=self.scan_seconds)
                self.status = f"Speed: {self.scan_seconds:.2f} s per step (saved)."
            elif item.startswith("VOICE"):
                self.next_voice()
            elif item.startswith("TALKING SCAN"):
                self.toggle_audio_scan()
            elif item.startswith("LETTERS"):
                self.toggle_layout()
            elif item == "HELP SCREEN":
                self.show_help = True
            elif item == "CAREGIVER LINK":
                self.show_link = True
        elif kind == "pain":
            line = PAIN_SAY.get(item, f"My {item.lower()} hurts.")
            if item == "VERY BAD":
                self.alarm(line)
            else:
                self.say(line)
            self.last_spoken = line
            self.status = f'Said: "{line}"'
            self.show_pain = False
        elif kind == "history":                   # a saved sentence: one pick
            self.say(item)
            remember_sentence(item)
            self.last_spoken = item
            self.status = f'Said: "{item.capitalize()}"'
        elif kind == "suggest":                   # replace the partial word
            remember_word(item)
            before = self.text.split(" ")
            if len(before) >= 2:
                remember_pair(before[-2], item)
            words = self.text.split(" ")
            words[-1] = item
            self.text = " ".join(words) + " "
        elif kind == "letters":
            self.text += item
        elif item == "SPACE":
            ws = self.text.split(" ")
            remember_word(ws[-1])
            if len(ws) >= 2:
                remember_pair(ws[-2], ws[-1])
            self.text += " "
        elif item == "DEL":
            if self.text.endswith(" ") and self.text.strip():
                # right after a finished word, DEL removes the whole word
                # (fixes a wrong suggestion in one pick instead of 6)
                self.text = self.text.rstrip()
                self.text = self.text[:self.text.rfind(" ") + 1]
                self.status = "Deleted last word."
            else:
                self.text = self.text[:-1]
        elif item == "CLEAR":
            self.text = ""
            self.presses = 0
        elif item == "SPEAK":
            self.say(self.text)
            remember_sentence(self.text)
            self.last_spoken = self.text
            self.status = "Speaking..."
            self.message_done(self.text)
        elif item == "HOME":
            self.go_page("HOME")
        elif item == "REPEAT":
            self.say(self.last_spoken)
            self.status = "Repeating." if self.last_spoken.strip() else "Nothing to repeat yet."
        elif item == "REST":
            self.resting = True
            self.status = "Resting. Hold a blink 1.5 s (or press SPACE) to wake."
        elif item in ("SLOWER", "FASTER"):
            step = 0.25 if item == "SLOWER" else -0.25
            self.scan_seconds = min(MAX_SCAN, max(MIN_SCAN, self.scan_seconds + step))
            save_settings(scan_seconds=self.scan_seconds)
            self.status = "Scan speed changed (saved)."

    # ---------- drawing ----------
    def draw_yesno(self, screen, font, big_font, small_font):
        W, H = screen.get_size()
        screen.fill(WHITE)
        huge = pygame.font.SysFont(None, int(H * 0.22))
        colors = {"YES": (120, 200, 130), "NO": (235, 120, 120)}
        top = 20
        if self.question:                   # caregiver's question across the top
            qrect = pygame.Rect(20, 20, W - 40, 100)
            pygame.draw.rect(screen, (237, 233, 254), qrect, border_radius=14)
            lines = fit_label(self.question, qrect, (big_font, font, small_font), BLACK)
            ty = qrect.centery - sum(l.get_height() for l in lines) // 2
            for l in lines:
                screen.blit(l, l.get_rect(midtop=(qrect.centerx, ty)))
                ty += l.get_height()
            top = 135
        for i, label in enumerate(["YES", "NO"]):
            rect = pygame.Rect(20 + i * (W - 40) // 2, top, (W - 40) // 2 - 10, H - 140 - top)
            lit = self.index == i
            pygame.draw.rect(screen, HIGHLIGHT if lit else colors[label], rect, border_radius=20)
            if lit:
                pygame.draw.rect(screen, BLACK, rect, width=8, border_radius=20)
            surf = huge.render(label, True, BLACK)
            screen.blit(surf, surf.get_rect(center=rect.center))
        rect = pygame.Rect(20, H - 125, W - 40, 70)
        lit = self.index == 2
        pygame.draw.rect(screen, HIGHLIGHT if lit else CONTROL, rect, border_radius=10)
        if lit:
            pygame.draw.rect(screen, BLACK, rect, width=4, border_radius=10)
        surf = font.render("BACK", True, BLACK)
        screen.blit(surf, surf.get_rect(center=rect.center))
        screen.blit(small_font.render(self.status, True, DIM), (24, H - 34))

    def draw(self, screen, font, big_font, small_font):
        if self.yesno:
            self.draw_yesno(screen, font, big_font, small_font)
            self.draw_overlays(screen, font, big_font, small_font)
            return
        W, H = screen.get_size()
        screen.fill(WHITE)
        box_h = 90
        pygame.draw.rect(screen, GRAY, (20, 20, W - 40, box_h), border_radius=10)
        lines, line = [], ""
        for word in (self.text + "|").split(" "):
            trial = (line + " " + word).strip()
            if big_font.size(trial)[0] > W - 90 and line:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
        lines = lines[-2:]
        if not self.text and self.page != "KEYBOARD":
            # nothing typed: show the day and time (easy to lose track in a hospital)
            now = time.localtime()
            hour = time.strftime("%I:%M %p", now).lstrip("0")
            lines = [time.strftime("%A", now) + "  " + hour]
        two = len(lines) > 1
        txt_font = font if two else big_font
        for i, ln in enumerate(lines):
            y0 = 45 if not two else 28 + i * 40
            ink = BLACK if self.text or self.page == "KEYBOARD" else DIM
            screen.blit(txt_font.render(ln, True, ink), (40, y0))

        rows = self.rows()
        top, bottom = 135, H - 50
        pitch = min(120, (bottom - top) / len(rows))
        y = top
        for r, (kind, items) in enumerate(rows):
            selected = self.mode == "item" and (kind, items) == self.row
            shown = items + ["BACK"] if selected else items
            cell_w = (W - 40) / max(len(shown), 1)
            for c, label in enumerate(shown):
                rect = pygame.Rect(20 + c * cell_w, y, cell_w - 6, pitch - 12)
                lit = (self.mode == "row" and r == self.index) or (selected and c == self.index)
                if kind == "menu":
                    base = TILE_COLORS.get(label, GRAY)
                elif kind == "phrase":
                    base = (255, 170, 170) if is_alert(label) else TILE_COLORS.get(self.page, GRAY)
                elif kind == "nav":
                    base = CONTROL
                else:
                    base = ROW_COLORS.get(kind, GRAY)
                color = HIGHLIGHT if lit else base
                pygame.draw.rect(screen, color, rect, border_radius=8)
                if lit:
                    pygame.draw.rect(screen, BLACK, rect, width=4, border_radius=8)
                text_color = BLACK if (self.mode == "row" or selected) else DIM
                tile_font = big_font if kind == "menu" else font
                lines = fit_label(label, rect, (tile_font, font, small_font), text_color)
                total = sum(sf.get_height() for sf in lines)
                ty = rect.centery - total // 2
                for sf in lines:
                    screen.blit(sf, sf.get_rect(midtop=(rect.centerx, ty)))
                    ty += sf.get_height()
            y += pitch

        audio = "    |    Talking scan: ON" if self.audio_scan else ""
        status = f"{self.status}    |    Speed: {self.scan_seconds:.2f} s{audio}"
        screen.blit(small_font.render(status, True, DIM), (24, H - 34))

        if self.camera_label:
            cx, cy = W - 40, H - 26
            dot = {True: (60, 180, 90), False: (220, 70, 70)}.get(self.face_seen, (240, 180, 40))
            pygame.draw.circle(screen, dot, (cx, cy), 9)
            label = self.camera_label[:60]
            surf = small_font.render(label, True, DIM)
            pygame.draw.rect(screen, WHITE, (cx - 26 - surf.get_width(), cy - 12,
                                             surf.get_width() + 8, surf.get_height() + 4))
            screen.blit(surf, (cx - 20 - surf.get_width(), cy - 9))
        if self.blink_progress > 0:
            w = int((W - 40) * min(1.0, self.blink_progress))
            pygame.draw.rect(screen, HIGHLIGHT, (20, 116, w, 10), border_radius=5)
        if self.presses:
            tag = small_font.render(f"presses: {self.presses}", True, DIM)
            screen.blit(tag, (W - 30 - tag.get_width(), 28))
        title = small_font.render(self.page, True, DIM)          # which page we're on
        screen.blit(title, (W - 30 - title.get_width(), 84))
        self.draw_overlays(screen, font, big_font, small_font)

    def draw_overlays(self, screen, font, big_font, small_font):
        W, H = screen.get_size()
        if self.banner and pygame.time.get_ticks() < self.banner_until:
            # message from the caregiver's phone
            box = pygame.Rect(40, H // 2 - 70, W - 80, 140)
            pygame.draw.rect(screen, (124, 58, 237), box, border_radius=18)
            head = small_font.render("MESSAGE FROM YOUR CAREGIVER", True, (230, 220, 255))
            screen.blit(head, head.get_rect(midtop=(box.centerx, box.y + 14)))
            inner = box.inflate(-30, -50).move(0, 14)
            lines = fit_label(self.banner, inner, (big_font, font, small_font), WHITE)
            ty = inner.centery - sum(l.get_height() for l in lines) // 2
            for l in lines:
                screen.blit(l, l.get_rect(midtop=(inner.centerx, ty)))
                ty += l.get_height()
        if self.show_link:
            draw_link_screen(self, screen, font, big_font, small_font)
        if self.show_help:
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((20, 20, 30, 245))
            screen.blit(shade, (0, 0))
            title = big_font.render("Caregiver keys", True, WHITE)
            screen.blit(title, (60, 40))
            y = 40 + title.get_height() + 25
            step = min(46, (H - y - 70) // len(HELP_LINES))
            for key, what in HELP_LINES:
                screen.blit(font.render(key, True, HIGHLIGHT), (60, y))
                screen.blit(font.render(what, True, WHITE), (200, y))
                y += step
            tip = small_font.render("Press H to close. Scanning is paused.", True, GRAY)
            screen.blit(tip, (60, H - 50))
        if self.yesno and self.blink_progress > 0:
            w = int((W - 40) * min(1.0, self.blink_progress))
            pygame.draw.rect(screen, BLACK, (20, H - 50, w, 10), border_radius=5)
        now = pygame.time.get_ticks()
        if now < self.alarm_until and (now // 300) % 2 == 0:
            # flashing red frame so a caregiver who can't hear still notices
            pygame.draw.rect(screen, ALARM_RED, (0, 0, W, H), width=18)
            tag = big_font.render("HELP NEEDED", True, WHITE)
            box = tag.get_rect(center=(W // 2, 65)).inflate(40, 16)
            pygame.draw.rect(screen, ALARM_RED, box, border_radius=10)
            screen.blit(tag, tag.get_rect(center=box.center))

        if self.resting:
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((20, 20, 30, 190))
            screen.blit(shade, (0, 0))
            msg = big_font.render("Resting", True, WHITE)
            screen.blit(msg, msg.get_rect(center=(W // 2, H // 2 - 30)))
            sub = font.render("Hold a blink for 1.5 seconds to wake up", True, WHITE)
            screen.blit(sub, sub.get_rect(center=(W // 2, H // 2 + 25)))
            if self.blink_progress > 0:
                w = int(400 * min(1.0, self.blink_progress))
                pygame.draw.rect(screen, HIGHLIGHT, (W // 2 - 200, H // 2 + 60, w, 12), border_radius=6)


def blink_step(talker, blink, camera, blink_button, dt):
    """Take the newest camera reading and turn a long blink into a press."""
    if camera.error:
        raise RuntimeError(camera.error)
    ear, bl, ld = camera.reading_full()
    talker.face_seen = camera.face
    talker.camera_label = camera.message
    talker.paused = blink_button.eye_closed(ear, bl, ld)
    fired = blink_button.update(ear, dt, bl, ld)
    if talker.resting:
        # only a LONG blink wakes it, so normal use of the eyes is ignored
        talker.blink_progress = blink_button.closed_time / WAKE_SECONDS
        if blink_button.closed_time >= WAKE_SECONDS:
            talker.wake()
            blink_button.fired = True      # don't also select something
    else:
        if fired:
            talker.press()
        talker.blink_progress = (0.0 if blink_button.fired
                                 else blink_button.closed_time / blink.HOLD_SECONDS)


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("One-Button Talker")

    def make_fonts(size):
        scale = max(0.8, min(1.6, size[1] / HEIGHT))
        return (pygame.font.SysFont(None, int(38 * scale)),
                pygame.font.SysFont(None, int(56 * scale)),
                pygame.font.SysFont(None, int(26 * scale)))

    font, big_font, small_font = make_fonts(screen.get_size())
    fullscreen = False
    clock = pygame.time.Clock()
    make_pages_file()
    talker = Talker()
    make_phone_file()

    # Caregiver Companion: a private web page for a caregiver's phone
    care = None
    try:
        import care_server
        care = care_server.CareLink()
        if care.start():
            talker.care = care
            print("Caregiver link:", care.url())
            talker.status = "Caregiver link ready - press C (or SETTINGS > CAREGIVER LINK) to see it."
        else:
            care = None
    except Exception as e:
        print("Caregiver link off:", e)
        care = None

    # Blink-to-select: the camera runs in its own process (camera_worker.py);
    # if anything goes wrong, SPACE / a switch still works.
    camera = None
    try:
        import blink
        camera = blink.EyeCamera()
        blink_button = blink.BlinkButton()
        talker.camera_label = camera.message
    except Exception as e:
        print("Blink control off:", e)
        blink = blink_button = None

    running = True
    while running:
        dt = clock.tick(30) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == SWITCH_KEY:
                talker.press()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_c:
                talker.show_link = not talker.show_link
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_h:
                talker.show_help = not talker.show_help
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_l:
                talker.toggle_layout()           # caregiver key: SMART / ABC letters
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_v:
                talker.next_voice()              # caregiver key: next voice
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_y:
                talker.yesno = not talker.yesno  # caregiver key: yes/no screen
                talker.index, talker.timer, talker.mode = 0, 0.0, "row"
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_a:
                talker.toggle_audio_scan()       # caregiver key: talking scan on/off
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_f:
                fullscreen = not fullscreen
                screen = (pygame.display.set_mode((0, 0), pygame.FULLSCREEN) if fullscreen
                          else pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE))
                font, big_font, small_font = make_fonts(screen.get_size())
            elif event.type == pygame.VIDEORESIZE:
                font, big_font, small_font = make_fonts(screen.get_size())

        if blink_button:
            try:
                blink_step(talker, blink, camera, blink_button, dt)
            except Exception as e:
                # camera problem: keep the app running on SPACE only
                print("Blink control stopped:", e)
                blink_button = None
                talker.face_seen, talker.paused, talker.blink_progress = False, False, 0.0
                talker.camera_label = "camera off"
                talker.status = f"Camera: {e}"

        talker.poll_care()
        talker.update(dt)
        talker.draw(screen, font, big_font, small_font)
        pygame.display.flip()
    if camera:
        camera.stop()
    if care:
        care.stop()
    pygame.quit()


if __name__ == "__main__":
    main()
