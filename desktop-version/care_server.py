"""
Caregiver Companion for One-Button Talker.

The patient's laptop runs this small private web server. A caregiver opens
the link on their phone (same Wi-Fi) and can:
  - see everything the patient says, live
  - get help alerts and answer "I'm coming"
  - ask a yes/no question (it appears and is read out on the patient's screen)
  - send a short message to the patient's screen
  - see if the patient is awake or resting and when they last pressed

No account and no outside server: messages never leave the home network.
A secret key in the link keeps other people on the Wi-Fi out.
"""
import json
import os
import random
import socket
import string
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "caregiver.html")
MAX_EVENTS = 300
MAX_TEXT = 120


def local_ip():
    """This laptop's address on the Wi-Fi (no data is actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def clean(text):
    """Keep caregiver text short and printable."""
    text = " ".join(str(text).split())
    return "".join(ch for ch in text if ch.isprintable())[:MAX_TEXT]


class CareLink:
    """Shared between the app (main thread) and the web server (other threads)."""

    def __init__(self, port=8765, key=None):
        self.key = key or "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        self.lock = threading.Lock()
        self.events = []            # {"id", "t", "kind", "text"}
        self.next_id = 1
        self.questions = []         # waiting to be shown on the patient's screen
        self.messages = []          # caregiver messages for the patient's screen
        self.status = {"page": "HOME", "resting": False, "last_press": time.time()}
        self.server = None
        self.port = port
        self.error = None

    # ----- called by the app -----
    def add(self, kind, text):
        """kind: said, alert, question, answer, message, info"""
        with self.lock:
            self.events.append({"id": self.next_id, "t": time.time(),
                                "kind": kind, "text": clean(text)})
            self.next_id += 1
            del self.events[:-MAX_EVENTS]

    def set_status(self, **kw):
        with self.lock:
            self.status.update(kw)

    def pop_question(self):
        with self.lock:
            return self.questions.pop(0) if self.questions else None

    def pop_message(self):
        with self.lock:
            return self.messages.pop(0) if self.messages else None

    # ----- called by the web server -----
    def state(self, since=0):
        with self.lock:
            return {"events": [e for e in self.events if e["id"] > since],
                    "status": dict(self.status), "now": time.time()}

    def ask(self, text):
        text = clean(text)
        if not text:
            return False
        with self.lock:
            self.questions.append(text)
        self.add("question", text)
        return True

    def send(self, text):
        text = clean(text)
        if not text:
            return False
        with self.lock:
            self.messages.append(text)
        self.add("message", text)
        return True

    # ----- server -----
    def url(self):
        return f"http://{local_ip()}:{self.port}/?key={self.key}"

    def start(self):
        """Start the web server in the background. Tries a few ports."""
        link = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):       # keep the Terminal quiet
                pass

            def _ok_key(self, query):
                return query.get("key", [""])[0] == link.key

            def _send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                if not self._ok_key(q):
                    return self._send(403, "Wrong or missing key. Use the link shown on the "
                                           "patient's screen.", "text/plain; charset=utf-8")
                if u.path == "/":
                    try:
                        with open(PAGE, "rb") as f:
                            return self._send(200, f.read(), "text/html; charset=utf-8")
                    except OSError:
                        return self._send(500, "caregiver.html is missing", "text/plain")
                if u.path == "/api/state":
                    try:
                        since = int(q.get("since", ["0"])[0])
                    except ValueError:
                        since = 0
                    return self._send(200, json.dumps(link.state(since)))
                self._send(404, "{}")

            def do_POST(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                if not self._ok_key(q):
                    return self._send(403, "{}")
                try:
                    n = min(int(self.headers.get("Content-Length", 0)), 2000)
                    body = json.loads(self.rfile.read(n) or b"{}")
                    text = body.get("text", "")
                except (ValueError, AttributeError):
                    return self._send(400, "{}")
                if u.path == "/api/ask":
                    ok = link.ask(text)
                elif u.path == "/api/message":
                    ok = link.send(text)
                else:
                    return self._send(404, "{}")
                self._send(200 if ok else 400, json.dumps({"ok": ok}))

        for port in range(self.port, self.port + 10):
            try:
                self.server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
                self.port = port
                break
            except OSError:
                continue
        if self.server is None:
            self.error = "no free port for the caregiver link"
            return False
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return True

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
