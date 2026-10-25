"""
Automated tests for One-Button Talker.

Run:  python3 tests.py
Runs without a camera, sound, or window, and uses a temporary folder,
so it never touches the real user's saved words or settings.
"""
import os
import shutil
import sys
import tempfile
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp()
for name in ("talker.py", "words.txt", "blink.py", "camera_worker.py"):
    shutil.copy(os.path.join(HERE, name), TMP)
sys.path.insert(0, TMP)

import pygame  # noqa: E402
import talker as t  # noqa: E402

_real_popen, _real_run = t.subprocess.Popen, t.subprocess.run


def _quiet(real):
    # block only the Mac speech/sound commands; let everything else run
    def wrapper(cmd, *a, **k):
        if isinstance(cmd, list) and cmd and cmd[0] in ("say", "afplay"):
            return None
        return real(cmd, *a, **k)
    return wrapper


t.subprocess.Popen = _quiet(_real_popen)   # no real speech/sounds in tests
t.subprocess.run = _quiet(_real_run)
t.phone_alert = lambda text: None


def pick(tk, kind, item):
    """Simulate the two presses it takes to pick `item` in a row of `kind`."""
    rows = tk.rows()
    r = next(i for i, (k, items) in enumerate(rows) if k == kind and item in items)
    tk.mode, tk.index = "row", r
    tk.press()
    tk.index = tk.row[1].index(item)
    tk.press()


class TalkerTests(unittest.TestCase):
    def setUp(self):
        t.USER_COUNTS.clear()
        t.USER_PAIRS.clear()
        t.SENTENCES.clear()
        for f in ("settings.json", "user_words.txt", "user_pairs.txt", "sentences.txt"):
            try:
                os.remove(os.path.join(TMP, f))
            except FileNotFoundError:
                pass
        self.tk = t.Talker()
        self.assertEqual(self.tk.page, "HOME")      # app opens on the home screen
        self.tk.go_page("KEYBOARD")                 # most tests use the keyboard

    # --- word prediction ---
    def test_patient_words_come_first(self):
        self.assertEqual(t.predict_words("WA")[:2], ["WATER", "WANT"])
        self.assertEqual(t.predict_words("BA")[0], "BATHROOM")
        self.assertEqual(t.predict_words("NU")[0], "NURSE")

    def test_next_word(self):
        self.assertIn("WATER", t.predict_next("NEED"))

    def test_typo_not_suggested_until_used_twice(self):
        t.remember_word("QXZY")
        self.assertNotIn("QXZY", t.predict_words("QX"))
        t.remember_word("QXZY")
        self.assertIn("QXZY", t.predict_words("QX"))

    # --- typing ---
    def test_spell_and_suggest(self):
        pick(self.tk, "letters", "H")
        pick(self.tk, "letters", "E")
        self.assertEqual(self.tk.text, "HE")
        pick(self.tk, "suggest", "HELP")
        self.assertEqual(self.tk.text, "HELP ")

    def test_del_removes_whole_word_after_suggestion(self):
        self.tk.text = "I NEED WATER "
        pick(self.tk, "control", "DEL")
        self.assertEqual(self.tk.text, "I NEED ")

    def test_del_removes_one_letter_mid_word(self):
        self.tk.text = "I NEED WAT"
        pick(self.tk, "control", "DEL")
        self.assertEqual(self.tk.text, "I NEED WA")

    def test_press_counter(self):
        pick(self.tk, "suggest", "I")
        pick(self.tk, "suggest", "NEED")
        pick(self.tk, "suggest", "WATER")
        pick(self.tk, "control", "SPEAK")
        self.assertIn("8 presses", self.tk.status)

    # --- features ---
    def test_sentence_history_row(self):
        self.tk.text = "I WANT TO GO TO BED"
        pick(self.tk, "control", "SPEAK")
        pick(self.tk, "control", "CLEAR")
        self.assertIn(("history", ["I WANT TO GO TO BED"]), self.tk.rows())

    def test_pain_follow_up(self):
        pick(self.tk, "quick", "I AM IN PAIN")
        kinds = [k for k, _ in self.tk.rows()]
        self.assertIn("pain", kinds)
        self.assertEqual(self.tk.index, kinds.index("pain"))   # highlight jumps there
        pick(self.tk, "pain", "STOMACH")
        self.assertEqual(self.tk.last_spoken, "My stomach hurts.")
        self.assertNotIn("pain", [k for k, _ in self.tk.rows()])

    def test_rest_and_wake(self):
        pick(self.tk, "control", "REST")
        self.assertTrue(self.tk.resting)
        idx = self.tk.index
        self.tk.update(10)
        self.assertEqual(self.tk.index, idx)                   # frozen while resting
        self.tk.press()
        self.assertFalse(self.tk.resting)

    def test_yes_no_screen(self):
        pick(self.tk, "control", "HOME")
        pick(self.tk, "menu", "YES / NO")
        self.assertTrue(self.tk.yesno)
        self.tk.index = 1
        self.tk.press()
        self.assertEqual(self.tk.last_spoken, "NO")
        self.tk.index = 2
        self.tk.press()
        self.assertFalse(self.tk.yesno)

    def test_settings_saved(self):
        pick(self.tk, "control", "HOME")
        pick(self.tk, "menu", "SETTINGS")
        pick(self.tk, "setting", "SLOWER")
        self.tk.toggle_layout()
        again = t.Talker()
        self.assertAlmostEqual(again.scan_seconds, 1.25)
        self.assertEqual(again.layout, "abc")

    def test_bad_settings_file_does_not_crash(self):
        with open(os.path.join(TMP, "settings.json"), "w") as f:
            f.write('{"scan_seconds": "fast"}')
        self.assertEqual(t.Talker().scan_seconds, t.START_SCAN_SECONDS)

    def test_weird_settings_files_do_not_crash(self):
        for bad in ("[]", "null", '{"voice": 5}', "not json"):
            with open(os.path.join(TMP, "settings.json"), "w") as f:
                f.write(bad)
            tk = t.Talker()
            self.assertIsNone(t.CURRENT_VOICE[0])
            tk.say("hello")

    def test_corrupt_learning_files_do_not_crash(self):
        import importlib
        with open(os.path.join(TMP, "user_pairs.txt"), "w") as f:
            f.write("CALL MAYA\nI\n")
        with open(os.path.join(TMP, "user_words.txt"), "w") as f:
            f.write("MAYA x\nWATER 3\n")
        importlib.reload(t)
        self.assertEqual(t.USER_PAIRS["CALL"]["MAYA"], 1)
        self.assertEqual(t.USER_COUNTS["WATER"], 3)

    def test_help_phrases_sound_alarm(self):
        self.assertTrue(t.is_alert("I NEED HELP"))
        self.assertTrue(t.is_alert("HELP ME"))
        self.assertFalse(t.is_alert("THANK YOU"))

    def test_talking_scan_quiet_during_alarm(self):
        said = []
        self.tk.audio_scan = True
        t.subprocess.Popen = lambda cmd, *a, **k: said.append(cmd)
        try:
            pick(self.tk, "quick", "I NEED HELP")
            said.clear()
            for _ in range(5):
                self.tk.update(2.0)
            self.assertEqual(said, [])
        finally:
            t.subprocess.Popen = _quiet(_real_popen)

    # --- home screen and pages ---
    def test_home_has_every_page(self):
        self.tk.go_page("HOME")
        tiles = [x for k, items in self.tk.rows() if k == "menu" for x in items]
        for name in ("KEYBOARD", "NEEDS", "FEELINGS", "PAIN", "PEOPLE", "CHAT",
                     "YES / NO", "SETTINGS", "REST"):
            self.assertIn(name, tiles)

    def test_phrase_page_speaks_and_returns_home(self):
        self.tk.go_page("HOME")
        pick(self.tk, "menu", "NEEDS")
        self.assertEqual(self.tk.page, "NEEDS")
        self.assertEqual(self.tk.index, 1)                      # starts on the phrases
        pick(self.tk, "phrase", "I AM THIRSTY")
        self.assertEqual(self.tk.last_spoken, "I AM THIRSTY")
        self.assertEqual(self.tk.page, "NEEDS")                 # stays for another pick
        self.assertEqual(self.tk.index, 1)                      # highlight on phrases
        pick(self.tk, "nav", "HOME")
        self.assertEqual(self.tk.page, "HOME")

    def test_emergency_phrases_sound_alarm(self):
        self.tk.go_page("PAIN")
        pick(self.tk, "phrase", "I CAN'T BREATHE WELL")
        self.assertGreater(self.tk.alarm_until, 0)

    def test_pain_quick_phrase_opens_pain_page(self):
        self.tk.go_page("HOME")
        pick(self.tk, "quick", "I AM IN PAIN")
        self.assertEqual(self.tk.page, "PAIN")
        self.assertEqual(self.tk.index, 1)

    def test_settings_page_controls(self):
        self.tk.go_page("SETTINGS")
        talking = [x for k, it in self.tk.rows() if k == "setting" for x in it
                   if x.startswith("TALKING")][0]
        pick(self.tk, "setting", talking)
        self.assertTrue(self.tk.audio_scan)
        letters = [x for k, it in self.tk.rows() if k == "setting" for x in it
                   if x.startswith("LETTERS")][0]
        pick(self.tk, "setting", letters)
        self.assertEqual(self.tk.layout, "abc")
        self.assertEqual(self.tk.page, "SETTINGS")

    def test_caregiver_pages_file(self):
        path = os.path.join(TMP, "pages.txt")
        with open(path, "w") as f:
            f.write("# my pages\n[family]\nCall Maya\nCall Grandma\n[HOME]\nignored\n")
        try:
            pages = t.load_pages()
            self.assertEqual(pages, [("FAMILY", ["CALL MAYA", "CALL GRANDMA"])])
        finally:
            os.remove(path)

    def test_every_page_draws(self):
        screen = pygame.display.set_mode((1000, 770))
        fonts = [pygame.font.SysFont(None, n) for n in (38, 56, 26)]
        for page in ["HOME", "KEYBOARD", "SETTINGS"] + self.tk.page_names():
            self.tk.go_page(page)
            self.tk.draw(screen, *fonts)

    # --- caregiver companion ---
    def test_caregiver_link_end_to_end(self):
        import json
        import urllib.request
        import urllib.error
        shutil.copy(os.path.join(HERE, "care_server.py"), TMP)
        shutil.copy(os.path.join(HERE, "caregiver.html"), TMP)
        import care_server
        link = care_server.CareLink(port=18765)
        self.assertTrue(link.start())
        base = f"http://127.0.0.1:{link.port}"
        try:
            # wrong key is refused
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "/api/state?key=nope")
            # the phone page loads with the key
            page = urllib.request.urlopen(f"{base}/?key={link.key}").read().decode()
            self.assertIn("Caregiver", page)

            self.tk.care = link
            self.tk.go_page("NEEDS")
            pick(self.tk, "phrase", "I AM THIRSTY")              # patient speaks

            req = urllib.request.Request(f"{base}/api/ask?key={link.key}",
                                         data=json.dumps({"text": "Are you cold?"}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req)                           # phone asks
            self.tk.poll_care()
            self.assertTrue(self.tk.yesno)
            self.assertEqual(self.tk.question, "Are you cold?")
            self.tk.index = 0
            self.tk.press()                                       # patient answers YES
            self.assertFalse(self.tk.yesno)
            self.assertEqual(self.tk.page, "NEEDS")               # back where they were

            state = json.loads(urllib.request.urlopen(
                f"{base}/api/state?key={link.key}&since=0").read())
            kinds = [(e["kind"], e["text"]) for e in state["events"]]
            self.assertIn(("said", "I AM THIRSTY"), kinds)
            self.assertIn(("question", "Are you cold?"), kinds)
            self.assertIn(("answer", "YES - Are you cold?"), kinds)
            self.assertEqual(state["status"]["page"], "NEEDS")

            pick(self.tk, "quick", "I NEED HELP")                 # alert reaches phone
            state = json.loads(urllib.request.urlopen(
                f"{base}/api/state?key={link.key}&since=0").read())
            self.assertIn(("alert", "I NEED HELP"), [(e["kind"], e["text"]) for e in state["events"]])

            req = urllib.request.Request(f"{base}/api/message?key={link.key}",
                                         data=json.dumps({"text": "I'm coming"}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req)                           # phone sends message
            self.tk.poll_care()
            self.assertEqual(self.tk.banner, "I'm coming")
        finally:
            self.tk.care = None
            link.stop()

    # --- blink detection (no camera needed) ---
    def _blink(self):
        import blink                     # the copy in the temporary folder
        return blink

    def test_looking_down_is_not_a_blink(self):
        blink = self._blink()
        b = blink.BlinkButton(calibration=None)
        for _ in range(50):
            b.update(0.50, 0.03, 0.05, 0.05)        # learn open eyes
        self.assertFalse(b.eye_closed(0.20, 0.40, 0.70))   # looking down: lids lower
        self.assertTrue(b.eye_closed(0.05, 0.90, 0.70))    # really closed while looking down
        self.assertTrue(b.eye_closed(0.20, 0.50, 0.05))    # closing while looking ahead
        fired = [b.update(0.20, 0.05, 0.40, 0.70) for _ in range(40)]   # look down 2 s
        self.assertNotIn(True, fired)

    def test_calibration_picks_best_signal(self):
        blink = self._blink()
        import random
        random.seed(2)
        r = lambda a, b: random.uniform(a, b)
        open_s = [(r(.48, .55), r(.02, .08)) for _ in range(60)]
        # EAR overlaps between looking down and closed, blink score does not
        down_s = [(r(.08, .20), r(.30, .45)) for _ in range(60)]
        closed_s = [(r(.05, .12), r(.70, .90)) for _ in range(60)]
        c = blink.compute_calibration(open_s, down_s, closed_s)
        self.assertTrue(c["ok"])
        self.assertEqual(c["signal"], "blink")
        self.assertTrue(0.45 < c["threshold"] < 0.70)
        b = blink.BlinkButton(calibration=c)
        self.assertFalse(b.eye_closed(0.15, 0.40, 0.6))
        self.assertTrue(b.eye_closed(0.08, 0.85, 0.6))

    def test_calibration_with_ear_only(self):
        blink = self._blink()
        open_s = [(0.5, None)] * 30
        down_s = [(0.25, None)] * 30
        closed_s = [(0.06, None)] * 30
        c = blink.compute_calibration(open_s, down_s, closed_s)
        self.assertEqual(c["signal"], "ear")
        self.assertAlmostEqual(c["threshold"], 0.155, places=3)

    def test_camera_line_parsing(self):
        blink = self._blink()
        import io
        cam = blink.EyeCamera.__new__(blink.EyeCamera)
        cam.ear = cam.blink_score = cam.look_down = cam.face = cam.error = None
        cam.message, cam._last = "", 0.0
        cam.proc = type("P", (), {"stdout": io.StringIO(
            "STATUS using camera 0\nEAR 0.4100 BL 0.120 LD 0.610\n")})()
        cam._read()                      # reads both lines, then 'camera stopped'
        self.assertEqual((cam.blink_score, cam.look_down), (0.12, 0.61))
        cam.proc = type("P", (), {"stdout": io.StringIO("EAR 0.4100\n")})()
        cam.error = None
        cam._read()
        self.assertIsNone(cam.blink_score)  # older format still works

    def test_smart_layout_has_every_letter_once(self):
        for rows in t.LAYOUTS.values():
            letters = "".join("".join(r) for r in rows)
            self.assertEqual(sorted(letters), sorted("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))

    def test_never_crashes_under_random_use(self):
        import random
        random.seed(1)
        screen = pygame.display.set_mode((1000, 770))
        fonts = [pygame.font.SysFont(None, n) for n in (38, 56, 26)]
        for _ in range(5000):
            self.tk.update(random.random())
            if random.random() < 0.3:
                self.tk.press()
            if random.random() < 0.01:
                self.tk.show_help = not self.tk.show_help
            if random.random() < 0.02:
                self.tk.go_page(random.choice(["HOME", "KEYBOARD", "SETTINGS"]
                                              + self.tk.page_names()))
        self.tk.draw(screen, *fonts)


if __name__ == "__main__":
    pygame.init()
    unittest.main(verbosity=2)
