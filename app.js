// One-Button Talker - phone / tablet app.
// One input (a tap anywhere, the space bar, or a long blink) drives everything:
// a highlight scans rows; press once to pick a row, again to pick an item.

import { QUICK, DEFAULT_PAGES, PAIN_PHRASES, LAYOUTS, isAlert, Words, chunks, load, save } from "./data.js";
import { EyeTracker, BlinkButton, WAKE_SECONDS, computeCalibration } from "./eyes.js";
import { Link, newKey } from "./link.js";

const $ = (id) => document.getElementById(id);
const MIN_SCAN = 0.5, MAX_SCAN = 3.0;
const CONTROL_ROW = ["SPACE", "DEL", "SPEAK", "REPEAT", "CLEAR", "HOME"];
const MENU_EXTRA = ["YES / NO", "SETTINGS", "REST"];
const PAIN_SCALE = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"];
const PAIN_ALARM = 8;          // a pain score this high also alerts the caregiver

// ---------- icons (simple line drawings) ----------
const ICONS = {
  KEYBOARD: '<rect x="2.5" y="6" width="19" height="12" rx="2.5"/><path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M7 14h10"/>',
  NEEDS: '<path d="M12 2.8c3.4 4.2 6.2 7.7 6.2 11a6.2 6.2 0 0 1-12.4 0c0-3.3 2.8-6.8 6.2-11z"/>',
  FEELINGS: '<circle cx="12" cy="12" r="9"/><path d="M8 14.2c1 1.4 2.4 2.1 4 2.1s3-.7 4-2.1M9 9.6h.01M15 9.6h.01"/>',
  PAIN: '<path d="M13 2 4.5 13.5H11l-1 8.5 8.5-11.5H12l1-8.5z"/>',
  PEOPLE: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.4-5.6 6.5-5.6s5.7 2 6.5 5.6"/><circle cx="17.5" cy="9" r="2.5"/><path d="M17.5 14.4c2.3.2 3.7 1.9 4.2 4.4"/>',
  CHAT: '<path d="M21 11.5a8.5 8.5 0 0 1-12.4 7.6L3 20.8l1.7-5.1A8.5 8.5 0 1 1 21 11.5z"/>',
  "YES / NO": '<path d="M4 12.5l4.5 4.5L20 5.5"/>',
  SETTINGS: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  REST: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  HOME: '<path d="M3.5 11 12 4l8.5 7v8.5a1 1 0 0 1-1 1H15v-6H9v6H4.5a1 1 0 0 1-1-1z"/>',
  BACK: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  SPEAK: '<path d="M4 9.5v5h4l5 4v-13l-5 4z"/><path d="M16.5 9a4.5 4.5 0 0 1 0 6M19 6.5a8 8 0 0 1 0 11"/>',
  HELP: '<path d="M6 16v-5a6 6 0 1 1 12 0v5l2 2H4z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
};
const icon = (name) => (ICONS[name] ? `<svg viewBox="0 0 24 24">${ICONS[name]}</svg>` : "");

// ---------- settings saved on this device ----------
const settings = Object.assign(
  { scan: 1.0, audioScan: false, layout: "smart", voice: null, camera: true, direct: false },
  load("settings", {}) || {}
);
settings.scan = Math.min(MAX_SCAN, Math.max(MIN_SCAN, Number(settings.scan) || 1.0));
if (!LAYOUTS[settings.layout]) settings.layout = "smart";
const saveSettings = () => save("settings", settings);

const pages = (() => {                 // caregivers can customise pages later; defaults for now
  const custom = load("pages", null);
  return Array.isArray(custom) && custom.length ? custom : DEFAULT_PAGES;
})();
const pageNames = pages.map(([n]) => n);

// ---------- My Phrases (typed by a caregiver, saved on this device) ----------
let myPhrases = load("myPhrases", []);

function saveMyPhrases(text) {
  myPhrases = text.split("\n")
    .map((line) => line.trim().toUpperCase())
    .filter((line) => line !== "")
    .slice(0, 15);
  save("myPhrases", myPhrases);
  _rowsKey = "";                      // tell the screen to rebuild with the new phrases
}

function openEditor() {
  $("phrasebox").value = myPhrases.join("\n");
  $("editor").classList.add("show");
  S.overlay = "editor";
}

function closeEditor() {
  $("editor").classList.remove("show");
  S.overlay = null;
}

$("savephrases").addEventListener("click", () => {
  saveMyPhrases($("phrasebox").value);
  closeEditor();
  goPage("MY PHRASES");
  S.status = "Saved " + myPhrases.length + " phrases.";
  render();
});

$("cancelphrases").addEventListener("click", () => {
  closeEditor();
  render();
});

// ---------- sound and speech ----------
let audio = null;
function audioCtx() {
  if (!audio) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) audio = new AC();
  }
  if (audio && audio.state === "suspended") audio.resume();
  return audio;
}
function tone(freq, start, dur, vol = 0.25, type = "sine", glideTo = null) {
  const a = audioCtx();
  if (!a) return;
  const o = a.createOscillator(), g = a.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, a.currentTime + start);
  if (glideTo) o.frequency.linearRampToValueAtTime(glideTo, a.currentTime + start + dur);
  g.gain.setValueAtTime(0.0001, a.currentTime + start);
  g.gain.exponentialRampToValueAtTime(vol, a.currentTime + start + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, a.currentTime + start + dur);
  o.connect(g).connect(a.destination);
  o.start(a.currentTime + start);
  o.stop(a.currentTime + start + dur + 0.05);
}
const click = () => tone(1200, 0, 0.05, 0.12, "triangle");
function siren() {               // three rising wails: hard to miss from another room
  for (let i = 0; i < 3; i++) tone(650, i * 0.75, 0.7, 0.5, "sawtooth", 1250);
}

let voices = [];
function loadVoices() {
  voices = (speechSynthesis.getVoices() || []).filter((v) => /^en/i.test(v.lang));
}
if ("speechSynthesis" in window) {
  loadVoices();
  speechSynthesis.onvoiceschanged = loadVoices;
}
const currentVoice = () => voices.find((v) => v.voiceURI === settings.voice) || null;
let realSpeech = false;
function speak(text, { rate = 1, scan = false } = {}) {
  if (!("speechSynthesis" in window) || !text.trim()) return;
  if (scan && realSpeech) return;                       // never talk over a real message
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.toLowerCase().replace(/\btv\b/g, "TV"));
  const v = currentVoice();
  if (v) u.voice = v;
  u.rate = rate;
  if (!scan) {
    realSpeech = true;
    u.onend = u.onerror = () => (realSpeech = false);
  }
  speechSynthesis.speak(u);
}

// ---------- app state ----------
const words = new Words();
const S = {
  page: "HOME", text: "", mode: "row", index: 0, row: null, timer: 0, loops: 0,
  paused: false, resting: false, yesno: false, question: null, overlay: null,
  presses: 0, lastSpoken: "", jumpTo: null, alarmUntil: 0, bannerUntil: 0,
  status: "Tap anywhere (or hold a blink) when your row lights up.", lastPress: Date.now(),
  started: false,
};

function rowsNow() {
  const quick = { kind: "quick", items: QUICK };
  if (S.page === "HOME") {
    return [quick, ...chunks(["KEYBOARD", ...pageNames, "MY PHRASES", ...MENU_EXTRA], 3).map((r) => ({ kind: "menu", items: r }))];
  }
  if (S.page === "SETTINGS") {
    const v = currentVoice();
    return [quick,
      { kind: "setting", items: ["SLOWER", "FASTER"] },
      { kind: "setting", items: ["VOICE: " + (v ? v.name.toUpperCase() : "DEFAULT"),
                                 "TALKING SCAN: " + (settings.audioScan ? "ON" : "OFF")] },
      { kind: "setting", items: ["LETTERS: " + settings.layout.toUpperCase(),
                                 "CAMERA: " + (settings.camera ? "ON" : "OFF")] },
      { kind: "setting", items: ["CALIBRATE CAMERA", "CAREGIVER LINK", "HELP"] },
      { kind: "setting", items: ["MODE: " + (settings.direct ? "TOUCH / EYE GAZE" : "SCAN")] },
      { kind: "nav", items: ["HOME"] }];
  }
  if (S.page === "MY PHRASES") {
    return [quick, ...chunks(myPhrases, 3).map((r) => ({ kind: "phrase", items: r })),
            { kind: "nav", items: ["HOME", "EDIT MY PHRASES"] }];
  }
  const page = pages.find(([n]) => n === S.page);
  if (page) {
    // PAIN page: a 0-10 pain scale first - the question every nurse and doctor asks
    const scale = S.page === "PAIN" ? [{ kind: "scale", items: PAIN_SCALE }] : [];
    return [quick, ...scale, ...chunks(page[1], 3).map((r) => ({ kind: "phrase", items: r })),
            { kind: "nav", items: ["HOME", "KEYBOARD"] }];
  }
  // KEYBOARD
  const rows = [quick];
  if (!S.text.trim()) {
    const recent = words.topSentences();
    if (recent.length) rows.push({ kind: "history", items: recent });
  }
  const ws = S.text.split(" ");
  const last = ws[ws.length - 1];
  const sugg = last ? words.predict(last) : words.next(ws.length >= 2 ? ws[ws.length - 2] : "");
  if (sugg.length) rows.push({ kind: "suggest", items: sugg });
  LAYOUTS[settings.layout].forEach((r) => rows.push({ kind: "letters", items: r }));
  rows.push({ kind: "control", items: CONTROL_ROW });
  return rows;
}
let _rows = null, _rowsKey = "";
function rows() {
  const key = [S.page, S.text, settings.layout, words.version, settings.audioScan, settings.scan,
               settings.voice, settings.camera, settings.direct, myPhrases.join("/")].join("|");
  if (key !== _rowsKey) { _rowsKey = key; _rows = rowsNow(); }
  return _rows;
}
function options() {
  if (S.yesno) return ["YES", "NO", "BACK"];
  if (S.mode === "row") return rows();
  return [...rows()[S.row].items, "BACK"];
}

// ---------- caregiver link ----------
let link = null;
const statusInfo = () => ({ page: S.page, resting: S.resting, lastPress: S.lastPress,
                            camera: eyes ? eyes.status : "off" });
function report(kind, text) {
  if (link) link.send("p", { k: kind, x: text, t: Date.now(), s: statusInfo() });
}
let statusTimer = null;
function reportStatusSoon() {
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => link && link.send("p", { k: "status", t: Date.now(), s: statusInfo() }), 2500);
}
async function startLink() {
  let key = load("linkKey", null);
  if (!key) { key = newKey(); save("linkKey", key); }
  try {
    link = await Link.open(key);
  } catch (e) {
    key = newKey(); save("linkKey", key);
    link = await Link.open(key);
  }
  link.listen("c", Math.floor(Date.now() / 1000), onCaregiver);
  setInterval(() => link && link.send("p", { k: "status", t: Date.now(), s: statusInfo() }), 60000);
  reportStatusSoon();
}
function onCaregiver(m) {
  const text = String(m.text || "").replace(/\s+/g, " ").trim().slice(0, 120);
  if (!text) return;
  if (m.type === "ask") {
    S.resting = false;
    S.overlay = null;
    S.question = text;
    S.yesno = true;
    S.mode = "row"; S.index = 0; S.timer = 0; S.loops = 0;
    speak("Question. " + text);
    report("question", text);
    S.status = "Caregiver question - answer YES or NO.";
  } else if (m.type === "msg") {
    $("bannertext").textContent = text;
    S.bannerUntil = Date.now() + 12000;
    speak("Message. " + text);
    report("message", text);
  }
  render();
}

// ---------- saying things ----------
function say(text) {
  speak(text);
  S.lastSpoken = text;
  report("said", text);
}
function alarm(text) {
  siren();
  setTimeout(() => speak(text), 2300);
  S.lastSpoken = text;
  S.alarmUntil = Date.now() + 6000;
  report("alert", text);
  if (link) link.sendAlertPush();
}

// ---------- navigation ----------
function goPage(name) {
  S.page = name;
  S.mode = "row"; S.index = 0; S.timer = 0; S.loops = 0;
  S.status = { HOME: "Home - pick a page.", KEYBOARD: "Keyboard - spell anything.",
               SETTINGS: "Settings - changes are saved." }[name] || cap(name) + " - pick a phrase.";
  reportStatusSoon();
}
const cap = (s) => s.charAt(0) + s.slice(1).toLowerCase();

// ---------- the one button ----------
function press() {
  if (!S.started) return;
  S.lastPress = Date.now();
  if (S.overlay) {                            // a press closes help / link screens
    if ((S.overlay === "calib" && calib.running) || S.overlay === "editor") return;
    S.overlay = null;
    render();
    return;
  }
  if (S.resting) { wake(); return; }
  if (S.yesno) {
    const choice = ["YES", "NO", "BACK"][S.index];
    click();
    if (choice === "BACK") {
      if (S.question) report("answer", "(closed without answering) " + S.question);
      S.question = null;
      S.yesno = false;
      S.status = "Back.";
    } else if (S.question) {
      speak(choice);
      report("answer", choice + " - " + S.question);
      S.status = `Answered ${choice}: "${S.question}"`;
      S.lastSpoken = choice;
      S.question = null;
      S.yesno = false;
    } else {
      say(choice);
      S.status = `Said: "${cap(choice)}"`;
    }
    S.mode = "row"; S.index = 0; S.timer = 0; S.loops = 0;
    render(); announce();
    return;
  }
  S.presses++;
  const opts = options();
  S.index %= opts.length;
  if (S.mode === "row") {
    S.row = S.index;
    S.mode = "item";
    S.index = 0;
  } else {
    const kind = rows()[S.row].kind;
    const item = opts[S.index];
    if (kind !== "quick" && item !== "SPEAK") click();
    choose(kind, item);
    S.mode = "row";
    S.index = restartRow(kind, item);
  }
  S.timer = 0; S.loops = 0;
  if (S.index >= options().length) S.index = 0;
  render(); announce();
}

function restartRow(kind, item) {
  if (S.jumpTo != null) { const j = S.jumpTo; S.jumpTo = null; return j; }
  if (S.page !== "KEYBOARD") return kind === "phrase" || kind === "scale" ? 1 : 0;   // stay on the phrases
  const typing = kind === "letters" || kind === "suggest" || item === "SPACE" || item === "DEL";
  if (!typing) return 0;
  const kinds = rows().map((r) => r.kind);
  return kinds.includes("suggest") ? kinds.indexOf("suggest") : kinds.indexOf("letters");
}

function choose(kind, item) {
  if (item === "BACK") return;
  if (["quick", "phrase", "history", "menu"].includes(kind) && !S.text.trim()) S.presses = 0;
  switch (kind) {
    case "quick":
    case "phrase":
      if (isAlert(item)) alarm(item); else say(item);
      S.status = `Said: "${cap(item)}"`;
      if (kind === "quick" && PAIN_PHRASES.has(item) && pageNames.includes("PAIN") && S.page !== "PAIN") {
        goPage("PAIN");
        S.jumpTo = 1;
        S.status = 'Said: "I am in pain" - how bad (0-10), and where?';
      }
      return;
    case "menu":
      if (item === "YES / NO") { S.yesno = true; S.status = "Yes / No - pick BACK to leave."; }
      else if (item === "REST") rest();
      else { goPage(item); if (pageNames.includes(item)) S.jumpTo = 1; }
      return;
    case "nav":
      if (item === "EDIT MY PHRASES") { openEditor(); return; }
      goPage(item);
      return;
    case "scale": {
      const n = Number(item);
      const line = `My pain is ${n} out of 10.`;
      if (n >= PAIN_ALARM) alarm(line); else say(line);
      S.status = `Said: "${line}"` + (n >= PAIN_ALARM ? " - caregiver alerted." : "");
      return;
    }
    case "history":
      say(item);
      words.learnSentence(item);
      S.status = `Said: "${cap(item)}"`;
      return;
    case "suggest": {
      words.learnWord(item);
      const ws = S.text.split(" ");
      if (ws.length >= 2) words.learnPair(ws[ws.length - 2], item);
      ws[ws.length - 1] = item;
      S.text = ws.join(" ") + " ";
      return;
    }
    case "letters":
      S.text += item;
      return;
    case "setting":
      return chooseSetting(item);
  }
  // control row
  if (item === "SPACE") {
    const ws = S.text.split(" ");
    words.learnWord(ws[ws.length - 1]);
    if (ws.length >= 2) words.learnPair(ws[ws.length - 2], ws[ws.length - 1]);
    S.text += " ";
  } else if (item === "DEL") {
    if (S.text.endsWith(" ") && S.text.trim()) {   // right after a word: delete the whole word
      const t = S.text.trimEnd();
      S.text = t.slice(0, t.lastIndexOf(" ") + 1);
      S.status = "Deleted last word.";
    } else S.text = S.text.slice(0, -1);
  } else if (item === "CLEAR") {
    S.text = ""; S.presses = 0;
  } else if (item === "SPEAK") {
    if (!S.text.trim()) { S.status = "Nothing typed yet."; return; }
    say(S.text.trim());
    words.learnSentence(S.text);
    const letters = S.text.trim().length, spelled = 2 * letters + 2;
    const fewer = Math.max(0, Math.round((100 * (spelled - S.presses)) / spelled));
    S.status = `Said in ${S.presses} presses (spelling it letter by letter: ${spelled}) - ${fewer}% fewer.`;
    S.presses = 0;
  } else if (item === "REPEAT") {
    if (S.lastSpoken) { speak(S.lastSpoken); S.status = "Repeating."; } else S.status = "Nothing to repeat yet.";
  } else if (item === "HOME") {
    goPage("HOME");
  }
}

function chooseSetting(item) {
  if (item === "SLOWER" || item === "FASTER") {
    settings.scan = Math.min(MAX_SCAN, Math.max(MIN_SCAN, settings.scan + (item === "SLOWER" ? 0.25 : -0.25)));
    S.status = `Speed: ${settings.scan.toFixed(2)} s per step.`;
  } else if (item.startsWith("VOICE")) {
    loadVoices();
    if (voices.length) {
      const i = voices.findIndex((v) => v.voiceURI === settings.voice);
      const next = voices[(i + 1) % voices.length];
      settings.voice = next.voiceURI;
      S.status = `Voice: ${next.name} (${voices.length} voices - pick again for the next).`;
    }
    speak("Hello, this is my voice.");
  } else if (item.startsWith("TALKING SCAN")) {
    settings.audioScan = !settings.audioScan;
    S.status = "Talking scan " + (settings.audioScan ? "on: rows and letters are read out loud." : "off.");
  } else if (item.startsWith("LETTERS")) {
    settings.layout = settings.layout === "smart" ? "abc" : "smart";
    S.status = settings.layout === "smart" ? "Letters: SMART (most-used first)." : "Letters: ABC order.";
  } else if (item.startsWith("CAMERA")) {
    settings.camera = !settings.camera;
    if (settings.camera) startCamera(); else stopCamera();
  } else if (item === "CALIBRATE CAMERA") {
    startCalibration();
  } else if (item === "CAREGIVER LINK") {
    showLink();
  } else if (item === "HELP") {
    S.overlay = "help";
  } else if (item.startsWith("MODE")) {
    setDirect(!settings.direct);
  }
  saveSettings();
}

function rest() {
  S.resting = true;
  S.status = "Resting.";
  reportStatusSoon();
}
function wake() {
  S.resting = false;
  S.mode = "row"; S.index = 0; S.timer = 0; S.loops = 0;
  S.status = "Awake - scanning again.";
  reportStatusSoon();
  render();
}

// ---------- scanning clock ----------
function update(dt) {
  if (settings.direct) return;      // touch / eye-gaze mode: you pick tiles directly, nothing moves
  if (S.paused || S.resting || S.overlay) return;
  S.timer += dt;
  const wait = settings.scan * (S.index === 0 ? 1.5 : 1);   // first item waits longer
  if (S.timer < wait) return;
  S.timer = 0;
  S.index = (S.index + 1) % options().length;
  if (S.index === 0) {
    S.loops++;
    if (S.mode === "item" && S.loops >= 2 && !S.yesno) {     // nothing picked: back out
      S.mode = "row"; S.index = 0; S.loops = 0;
      S.status = "No pick - back to all rows.";
      render();
    }
  }
  highlight();
  announce();
}

const ROW_NAMES = { quick: "phrases", suggest: "words", control: "controls", history: "recent",
                    scale: "pain scale" };
function announce() {
  if (!settings.audioScan || Date.now() < S.alarmUntil + 3000) return;
  const opts = options();
  const it = opts[S.index];
  if (it == null) return;
  let label;
  if (S.yesno || S.mode === "item") label = it;
  else if (it.kind === "letters") label = `${it.items[0]} to ${it.items[it.items.length - 1]}`;
  else if (it.kind === "phrase") label = it.items[0];
  else label = ROW_NAMES[it.kind] || it.items.join(", ");
  speak(label, { rate: 1.3, scan: true });
}

// ---------- drawing ----------
let _structKey = "";
function render() {
  const rs = rows();
  const key = _rowsKey + "|" + S.mode + "|" + S.row;
  if (key !== _structKey) {
    _structKey = key;
    const grid = $("grid");
    grid.className = "p-" + S.page;
    grid.innerHTML = "";
    rs.forEach((r, ri) => {
      const row = document.createElement("div");
      row.className = "row " + r.kind;
      const items = S.mode === "item" && ri === S.row ? [...r.items, "BACK"] : r.items;
      row.style.setProperty("--n", items.length);
      items.forEach((label) => {
        const t = document.createElement("div");
        let cls = "tile " + (label === "BACK" ? "back" : r.kind);
        if ((r.kind === "phrase" || r.kind === "quick") && isAlert(label)) cls += " urgent";
        if (r.kind === "menu") cls += " c-" + label.replace(/[^A-Z]/g, "");
        if (r.kind === "scale" && label !== "BACK") {
          // green (0) to red (10), like the pain charts in hospitals
          t.style.setProperty("--hue", Math.round(130 - Number(label) * 13));
        }
        t.className = cls;
        t.dataset.r = ri;
        t.dataset.c = items.indexOf(label);
        const ic = r.kind === "menu" ? icon(label)
          : label === "BACK" ? icon("BACK") : label === "HOME" ? icon("HOME")
          : label === "SPEAK" ? icon("SPEAK") : label === "I NEED HELP" ? icon("HELP") : "";
        t.innerHTML = ic + `<span class="lbl"></span>`;
        t.querySelector(".lbl").textContent = label;
        row.appendChild(t);
      });
      grid.appendChild(row);
    });
  }
  highlight();
  // page title, message, footer
  $("pagename").textContent = S.page === "HOME" ? (innerWidth < 560 ? "Talker" : "One-Button Talker") : cap(S.page);
  const msg = $("msgtext");
  if (S.text) {
    msg.className = "";
    msg.textContent = S.text;
    const c = document.createElement("span"); c.className = "caret"; msg.appendChild(c);
  } else {
    msg.className = "empty";
    msg.textContent = S.page === "KEYBOARD" ? "Start spelling…"
      : new Date().toLocaleString([], { weekday: "long", hour: "numeric", minute: "2-digit" });
  }
  $("msgcount").textContent = S.presses && S.page === "KEYBOARD" ? `presses: ${S.presses}` : "";
  $("status").textContent = S.status;
  $("speed").textContent = `Speed ${settings.scan.toFixed(2)} s` + (settings.audioScan ? " · talking scan" : "");
  // overlays
  for (const id of ["help", "linkview", "calib"]) $(id).classList.toggle("show", S.overlay === ({ help: "help", linkview: "link", calib: "calib" })[id]);
  $("yesno").classList.toggle("show", S.yesno);
  $("yesno").classList.toggle("asked", !!S.question);
  $("ynq").textContent = S.question || "";
  $("rest").classList.toggle("show", S.resting);
}

function highlight() {
  const rowsEl = $("grid").children;
  for (let r = 0; r < rowsEl.length; r++) {
    const rowEl = rowsEl[r];
    rowEl.classList.toggle("dim", S.mode === "item" && r !== S.row);
    const tiles = rowEl.children;
    for (let c = 0; c < tiles.length; c++) {
      const lit = !settings.direct && !S.yesno &&
        ((S.mode === "row" && r === S.index) || (S.mode === "item" && r === S.row && c === S.index));
      tiles[c].classList.toggle("lit", lit);
    }
  }
  ["yn-yes", "yn-no", "yn-back"].forEach((id, i) => $(id).classList.toggle("lit", !settings.direct && S.yesno && S.index === i));
}

function drawLive() {
  const now = Date.now();
  $("alarm").classList.toggle("show", now < S.alarmUntil);
  $("banner").classList.toggle("show", now < S.bannerUntil);
  // camera pill
  const pill = $("campill");
  const st = eyes ? eyes.status : "off";
  pill.classList.toggle("on", st === "tracked" || st === "noface");
  $("camdot").style.background = { tracked: "var(--ok)", noface: "var(--bad)", starting: "var(--warn)",
                                   error: "var(--bad)" }[st] || "var(--muted)";
  $("camtext").textContent = eyes ? eyes.message : "camera off";
  // big, plain help at the bottom when the camera is on but can't see a blink yet
  if (eyes && eyes.stream && st !== "tracked") {
    $("status").textContent = st === "noface"
      ? "Camera can't see your face: sit 1-2 feet away with light in front of you."
      : "Camera: " + eyes.message;
  } else if (eyes && st === "error") {
    $("status").textContent = "Camera: " + eyes.message + ". Tap still works.";
  } else if ($("status").textContent !== S.status) {
    $("status").textContent = S.status;
  }
  const r = eyes && eyes.reading();
  const open = r && blinkBtn.baseline ? Math.max(0, Math.min(1, r.ear / blinkBtn.baseline)) : 0;
  const meter = $("eyemeter").firstElementChild;
  meter.style.width = Math.round(open * 100) + "%";
  meter.style.background = r && blinkBtn.closed(r) ? "var(--lit)" : "var(--ok)";
  // blink progress
  const prog = blinkBtn.fired ? 0 : blinkBtn.closedTime;
  $("blinkbar").style.width = S.resting ? "0" : Math.min(100, (prog / 0.35) * 100) + "%";
  $("restbar").firstElementChild.style.width = Math.min(100, (blinkBtn.closedTime / WAKE_SECONDS) * 100) + "%";
  // link pill
  $("linkpill").classList.toggle("show", !!(link && link.connected));
  // clock on empty message (once a minute is enough, but this is cheap)
  if (!S.text && S.page !== "KEYBOARD" && now % 15000 < 40) render();
}

// ---------- camera / blink ----------
let eyes = null;
let blinkBtn = new BlinkButton();
async function startCamera() {
  if (eyes && eyes.stream) return;
  eyes = eyes || new EyeTracker($("video"));
  const ok = await eyes.start();
  if (!ok) S.status = "Camera: " + eyes.message;
  render();
}
function stopCamera() {
  if (eyes) eyes.stop();
  S.paused = false;
}

function blinkStep(dt) {
  if (!eyes || !eyes.stream) return;
  eyes.step();
  const r = eyes.reading();
  if (calib.collecting) {
    if (r && eyes.frameId !== calib.lastFrame) { calib.lastFrame = eyes.frameId; calib.samples.push(r); }
    return;
  }
  S.paused = blinkBtn.closed(r) && !S.overlay;
  const fired = blinkBtn.update(r, dt);
  if (S.resting) {
    if (blinkBtn.closedTime >= WAKE_SECONDS) { blinkBtn.fired = true; wake(); }
  } else if (fired) {
    press();
  }
}

// ---------- calibration (look at screen / look down / close eyes) ----------
const calib = { running: false, collecting: false, samples: [], lastFrame: -1 };
const sleep = (ms) => new Promise((res) => setTimeout(res, ms));
async function collect(seconds, settle) {
  await sleep(settle * 1000);
  calib.samples = []; calib.collecting = true;
  const fg = $("calibfg"), t0 = Date.now();
  while (Date.now() - t0 < seconds * 1000) {
    fg.style.strokeDashoffset = 327 * (1 - (Date.now() - t0) / (seconds * 1000));
    await sleep(50);
  }
  calib.collecting = false;
  fg.style.strokeDashoffset = 327;
  return calib.samples;
}
async function startCalibration() {
  if (!eyes || eyes.status !== "tracked") {
    S.status = "Calibration needs the camera to see your face first.";
    if (!settings.camera) { settings.camera = true; saveSettings(); startCamera(); }
    return;
  }
  S.overlay = "calib"; calib.running = true;
  $("calibresult").innerHTML = "";
  $("calibhint").textContent = "Follow the voice. It takes about 20 seconds.";
  render();
  const step = async (text, voice, secs, settle) => {
    $("calibstep").textContent = text;
    speak(voice);
    return collect(secs, settle);
  };
  const open = await step("Look at the screen", "Calibration. Look at the screen normally.", 3.5, 2.5);
  const down = await step("Look DOWN, eyes open", "Now look down at the bottom of the screen. Keep your eyes open.", 3.5, 3);
  const closed = await step("Close your eyes", "Now close your eyes until the beep.", 3, 2.4);
  tone(880, 0, 0.25, 0.3); tone(1320, 0.25, 0.3, 0.3);
  calib.running = false;
  if (Math.min(open.length, down.length, closed.length) < 8) {
    $("calibstep").textContent = "Couldn't see your face well enough";
    $("calibhint").textContent = "Try again with more light on your face. Tap to close.";
    speak("Open your eyes. Calibration didn't work, please try again with more light.");
    return;
  }
  const c = computeCalibration(open, down, closed);
  save("calibration", c);
  blinkBtn = new BlinkButton(c);
  $("calibstep").textContent = c.ok ? "Done ✓" : "Done - but it's close";
  $("calibresult").innerHTML =
    `<table id="calibtable"><tr><td>Looking at screen</td><td>${c.openEar.toFixed(3)}</td></tr>` +
    `<tr><td>Looking down</td><td>${c.downEar.toFixed(3)}</td></tr>` +
    `<tr><td>Eyes closed</td><td>${c.closedEar.toFixed(3)}</td></tr>` +
    `<tr><td>Using</td><td>${c.signal === "blink" ? "blink score" : "eye openness"}</td></tr></table>`;
  $("calibhint").textContent = c.ok
    ? "Looking down will no longer count as a blink. Tap to close."
    : "Looking down and closing your eyes look similar. Raise the phone to eye level and try again. Tap to close.";
  speak(c.ok ? "Open your eyes. Done. Looking down will no longer count as a blink."
             : "Open your eyes. Done, but try raising the screen to eye level.");
}

// ---------- caregiver link screen ----------
function showLink() {
  if (!link) { S.status = "Caregiver link is still starting…"; return; }
  const url = link.caregiverUrl();
  try {
    const q = qrcode(0, "M");
    q.addData(url);
    q.make();
    $("qr").innerHTML = q.createSvgTag({ cellSize: 6, margin: 2, scalable: true });
  } catch (e) {
    $("qr").textContent = "";
  }
  $("linkurl").textContent = url;
  S.overlay = "link";
}
$("sharelink").addEventListener("pointerdown", async (e) => {
  e.stopPropagation();
  const url = link && link.caregiverUrl();
  if (!url) return;
  try {
    if (navigator.share) await navigator.share({ title: "One-Button Talker - caregiver link", url });
    else { await navigator.clipboard.writeText(url); $("sharelink").textContent = "Copied!"; }
  } catch (err) { /* cancelled */ }
});
$("newlink").addEventListener("pointerdown", async (e) => {
  e.stopPropagation();
  if (link) link.close();
  save("linkKey", newKey());
  await startLink();
  showLink();
  render();
});

// ---------- input: tap anywhere, keyboard, blink ----------
document.addEventListener("pointerdown", (e) => {
  if (!S.started || e.target.closest("button, #editor")) return;
  e.preventDefault();
  audioCtx();
  if (settings.direct) touchSelect(e.target); else press();
}, { passive: false });

// ---------- touch / eye-gaze mode ----------
// The tile you touch is picked directly. With Apple's Eye Tracking turned on
// (Settings > Accessibility > Eye Tracking), looking at a tile and holding your
// gaze makes iOS tap it - so you select by LOOKING, with no moving highlight.
function touchSelect(target) {
  S.lastPress = Date.now();
  if (S.overlay) { if (!(S.overlay === "calib" && calib.running)) { S.overlay = null; render(); } return; }
  if (S.resting) { wake(); return; }
  if (S.yesno) {
    const i = { "yn-yes": 0, "yn-no": 1, "yn-back": 2 }[target.closest(".tile")?.id];
    if (i == null) return;
    S.index = i;
    press();                    // same YES / NO / BACK handling as scanning
    return;
  }
  const tile = target.closest("#grid .tile");
  if (!tile) return;
  const r = Number(tile.dataset.r), c = Number(tile.dataset.c);
  const row = rows()[r];
  if (!row || row.items[c] == null) return;
  S.presses++;
  const kind = row.kind, item = row.items[c];
  tile.classList.add("lit");                       // quick flash so you see what was picked
  setTimeout(() => tile.classList.remove("lit"), 250);
  if (kind !== "quick" && item !== "SPEAK") click();
  S.mode = "row";
  choose(kind, item);
  S.jumpTo = null;
  S.index = 0;
  render();
}

function setDirect(on) {
  settings.direct = on;
  saveSettings();
  S.mode = "row"; S.index = 0; S.timer = 0;
  if (on) {
    // Apple's Eye Tracking needs the front camera, so our blink camera steps aside
    stopCamera();
    settings.camera = false;
    S.status = "Touch / eye-gaze mode: tap (or look and hold) on any tile.";
  } else {
    S.status = "Scan mode: tap anywhere, or blink, when your row lights up.";
  }
  saveSettings();
  render();
}
document.addEventListener("keydown", (e) => {
  if (!S.started || S.overlay === "editor") return;
    const k = e.key.toLowerCase();
  if (k === " " || k === "enter") { e.preventDefault(); if (!e.repeat) press(); }
  else if (k === "h") { S.overlay = S.overlay === "help" ? null : "help"; render(); }
  else if (k === "c") { if (S.overlay === "link") S.overlay = null; else showLink(); render(); }
  else if (k === "y") { S.yesno = !S.yesno; S.index = 0; S.timer = 0; render(); }
  else if (k === "f") { document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.(); }
});

// keep the screen on: a communication device must never go to sleep on its own
let wakeLock = null;
async function keepAwake() {
  try { wakeLock = await navigator.wakeLock?.request("screen"); } catch (e) { /* not supported */ }
}
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") keepAwake(); });

// ---------- start ----------
async function begin(useCamera, direct = false) {
  S.started = true;
  settings.direct = direct;
  $("start").classList.remove("show");
  audioCtx();
  if ("speechSynthesis" in window) {             // unlocks speech on iPhone (needs a tap)
    const u = new SpeechSynthesisUtterance(" ");
    u.volume = 0;
    speechSynthesis.speak(u);
  }
  settings.camera = useCamera;
  saveSettings();
  keepAwake();
  render();
  if (useCamera) startCamera();
  startLink().catch(() => { S.status = "Caregiver link offline (no internet) - everything else works."; });
}
$("startcam").addEventListener("click", () => begin(true));
$("starttap").addEventListener("click", () => begin(false));
$("startgaze").addEventListener("click", () => begin(false, true));
if (/iphone|ipad|ipod/i.test(navigator.userAgent) && !navigator.standalone) $("installhint").style.display = "block";
if (settings.direct) {            // remember the last choice: put that button first
  $("startgaze").className = "btn"; $("startcam").className = "btn ghost";
  $("startgaze").parentNode.prepend($("startgaze"));
} else if (!settings.camera) {
  $("starttap").className = "btn"; $("startcam").className = "btn ghost";
  $("starttap").parentNode.prepend($("starttap"));
}

words.loadList().then(render);
render();

let last = performance.now();
function loop(now) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  if (S.started) {
    blinkStep(dt);
    update(dt);
  }
  drawLive();
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

// for automated tests
window.__talker = { S, press, rows, options, goPage, settings, words, onCaregiver, render,
                    get link() { return link; }, computeCalibration };
