// Caregiver page: live feed, help alerts, ask yes/no questions, send messages.
import { Link } from "./link.js";

const $ = (id) => document.getElementById(id);
const ASK = ["Are you in pain?", "Are you thirsty?", "Are you cold?", "Do you need the bathroom?",
             "Do you want to sleep?", "Are you okay?"];
const MSG = ["I'm coming", "Be right there", "I love you", "Try to rest", "The doctor is on the way"];
const LABEL = { said: "Said", alert: "🚨 HELP", question: "Question sent", answer: "Answer",
                message: "Message sent" };

let link, lastStatus = null, lastStatusAt = 0, lastAlert = null, ackAt = 0, audio = null;
const events = [];

function toast(t) {
  const el = $("toast");
  el.textContent = t;
  el.style.opacity = 1;
  clearTimeout(toast.h);
  toast.h = setTimeout(() => (el.style.opacity = 0), 2000);
}
const clock = (ms) => new Date(ms).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
function ago(ms) {
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 60) return s + "s ago";
  if (s < 3600) return Math.round(s / 60) + " min ago";
  return Math.round(s / 3600) + " h ago";
}
function beep() {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    [0, 0.35, 0.7].forEach((d) => {
      const o = audio.createOscillator(), g = audio.createGain();
      o.frequency.value = 880;
      o.connect(g).connect(audio.destination);
      g.gain.setValueAtTime(0.3, audio.currentTime + d);
      o.start(audio.currentTime + d);
      o.stop(audio.currentTime + d + 0.2);
    });
  } catch (e) { /* no sound */ }
}

function addToFeed(e) {
  $("empty").style.display = "none";
  const li = document.createElement("li");
  li.className = e.k;
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.innerHTML = "<span></span><span></span>";
  meta.children[0].textContent = LABEL[e.k] || e.k;
  meta.children[1].textContent = clock(e.t);
  const txt = document.createElement("div");
  txt.className = "txt";
  txt.textContent = e.x;
  li.append(meta, txt);
  // keep newest first even if history arrives out of order
  const items = [...$("feed").children];
  const before = items.find((el) => Number(el.dataset.t) < e.t);
  li.dataset.t = e.t;
  $("feed").insertBefore(li, before || null);
}

function onEvent(e, live) {
  if (typeof e.t !== "number") e.t = (e._time || Date.now() / 1000) * 1000;
  if (e.s && e.t >= lastStatusAt) { lastStatus = e.s; lastStatusAt = e.t; }
  if (e.k === "status" || !e.x) { showStatus(); return; }
  addToFeed(e);
  if (e.k === "alert" && Date.now() - e.t < 5 * 60 * 1000 && (!lastAlert || e.t > lastAlert.t)) {
    lastAlert = e;
    if (live) { if (navigator.vibrate) navigator.vibrate([400, 200, 400, 200, 400]); beep(); }
  }
  if (e.k === "message" && e.x === "I'm coming") ackAt = Math.max(ackAt, e.t);
  showAlert();
  showStatus();
}

function showAlert() {
  const on = lastAlert && lastAlert.t > ackAt;
  $("alert").style.display = on ? "block" : "none";
  if (on) $("alerttext").textContent = lastAlert.x;
}

function showStatus() {
  const online = lastStatusAt && Date.now() - lastStatusAt < 150000;
  if (!lastStatus) return;
  const s = lastStatus;
  $("pdot").style.background = !online ? "var(--muted)" : s.resting ? "#a5b4fc" : "var(--ok)";
  $("pstate").textContent = !online ? "App closed or offline" : s.resting ? "Resting" : "Awake";
  const page = String(s.page || "HOME").toLowerCase();
  $("psub").textContent = (online ? `On ${page} page · ` : "Last seen " + ago(lastStatusAt) + " · ") +
    "last press " + ago(s.lastPress || lastStatusAt) +
    (s.camera === "tracked" ? " · eyes tracked" : s.camera === "noface" ? " · face not in view" : "");
}

async function send(type, text) {
  text = text.trim();
  if (!text) return;
  const ok = await link.send("c", { type, text });
  toast(ok ? (type === "ask" ? "Asked: " : "Sent: ") + text : "Couldn't send - check your internet");
}

function chips(box, list, type) {
  list.forEach((text) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ghost";
    b.textContent = text;
    b.onclick = () => send(type, text);
    $(box).appendChild(b);
  });
}

async function main() {
  const key = new URLSearchParams(location.hash.slice(1)).get("k");
  if (!key) { $("ui").style.display = "none"; $("nokey").style.display = "block"; $("conntext").textContent = "No link"; return; }
  try {
    link = await Link.open(key);
  } catch (e) {
    $("ui").style.display = "none"; $("nokey").style.display = "block"; return;
  }
  $("alerttopic").textContent = link.alertTopic();
  $("copytopic").onclick = async () => {
    try { await navigator.clipboard.writeText(link.alertTopic()); toast("Copied"); } catch (e) { toast(link.alertTopic()); }
  };
  chips("askchips", ASK, "ask");
  chips("msgchips", MSG, "msg");
  $("askform").onsubmit = (e) => { e.preventDefault(); send("ask", $("askinput").value); $("askinput").value = ""; };
  $("msgform").onsubmit = (e) => { e.preventDefault(); send("msg", $("msginput").value); $("msginput").value = ""; };
  $("coming").onclick = () => { send("msg", "I'm coming"); ackAt = Date.now(); showAlert(); };
  document.addEventListener("click", () => { try { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); } catch (e) {} }, { once: true });

  const loadedAt = Date.now();
  link.listen("p", "12h", (e) => onEvent(e, Date.now() - loadedAt > 3000));   // history first, then live
  setInterval(() => {
    $("conndot").style.background = link.connected ? "var(--ok)" : "var(--bad)";
    $("conntext").textContent = link.connected ? "Connected" : "Reconnecting…";
    showStatus();
  }, 1000);
}
main();
