// One-Button Talker - phrases, pages, letter layouts and word prediction.
// Everything the person learns (their own words, word pairs, sentences)
// is saved on this device only (localStorage).

export const QUICK = ["YES", "NO", "I NEED HELP", "I AM IN PAIN", "THANK YOU"];

export const DEFAULT_PAGES = [
  ["NEEDS", ["I AM THIRSTY", "I AM HUNGRY", "I NEED THE BATHROOM",
             "I AM COLD", "I AM HOT", "PLEASE MOVE ME",
             "I WANT TO SLEEP", "TURN THE LIGHT OFF", "TURN THE TV ON",
             "I NEED MY MEDICINE", "PLEASE SUCTION ME", "I NEED MY GLASSES"]],
  ["FEELINGS", ["I AM OKAY", "I AM HAPPY", "I AM SAD",
                "I AM SCARED", "I AM TIRED", "I AM BORED",
                "I AM FRUSTRATED", "I FEEL BETTER", "I FEEL WORSE"]],
  ["PAIN", ["MY HEAD HURTS", "MY CHEST HURTS", "MY STOMACH HURTS",
            "MY BACK HURTS", "MY LEGS HURT", "MY ARMS HURT",
            "IT HURTS A LITTLE", "IT HURTS A LOT", "THE PAIN IS VERY BAD",
            "I FEEL SICK", "I FEEL DIZZY", "I CAN'T BREATHE WELL"]],
  ["PEOPLE", ["CALL THE NURSE", "CALL THE DOCTOR", "CALL MY FAMILY",
              "CALL MY MOM", "CALL MY DAD", "CALL MY FRIEND",
              "I WANT TO BE ALONE", "PLEASE STAY WITH ME", "WHEN ARE THEY COMING?"]],
  ["CHAT", ["HELLO", "GOODBYE", "HOW ARE YOU?",
            "I AM GOOD", "THANK YOU", "I LOVE YOU",
            "PLEASE WAIT", "I DON'T KNOW", "PLEASE SAY THAT AGAIN",
            "WHAT TIME IS IT?", "PLEASE TALK TO ME", "THAT'S FUNNY"]],
];

// Phrases that also sound the alarm (besides anything with the word HELP).
export const URGENT = new Set(["THE PAIN IS VERY BAD", "I CAN'T BREATHE WELL", "MY CHEST HURTS"]);
export const PAIN_PHRASES = new Set(["I AM IN PAIN", "I'M IN PAIN", "IT HURTS", "I HURT"]);
export const isAlert = (p) => p.split(/\s+/).includes("HELP") || URGENT.has(p);

// Two letter layouts. SMART puts the most-used English letters where the
// highlight reaches them first (steps = row + column). Averaged over how often
// each letter is used: 4.54 steps per letter vs 5.64 for ABC = ~20% less waiting.
export const LAYOUTS = {
  smart: ["ETOSLW", "AIHCFP", "NRUGBK", "DMYVJXQZ"].map((r) => r.split("")),
  abc: ["ABCDEF", "GHIJKL", "MNOPQR", "STUVWXYZ"].map((r) => r.split("")),
};

const NEXT_WORDS = {
  "": ["I", "PLEASE", "CAN"],
  I: ["NEED", "WANT", "AM", "FEEL", "LOVE"],
  NEED: ["WATER", "HELP", "BATHROOM", "NURSE", "MEDICINE", "REST"],
  WANT: ["WATER", "TO", "MY", "MORE"],
  AM: ["IN", "COLD", "HOT", "TIRED", "HUNGRY", "THIRSTY", "OKAY"],
  FEEL: ["SICK", "DIZZY", "BETTER", "WORSE", "TIRED", "PAIN"],
  IN: ["PAIN", "BED"],
  MY: ["HEAD", "STOMACH", "BACK", "CHEST", "LEGS", "FAMILY"],
  PLEASE: ["HELP", "CALL", "TURN", "MOVE", "STOP"],
  CALL: ["MY", "NURSE", "DOCTOR", "MOM", "DAD"],
  CAN: ["YOU", "I"],
  YOU: ["PLEASE", "HELP"],
  TURN: ["ME", "OFF", "ON"],
  THANK: ["YOU"],
  LOVE: ["YOU"],
  TO: ["SLEEP", "SIT", "EAT", "DRINK", "GO", "TALK"],
  PAIN: ["IS"],
  IS: ["SHARP", "BAD", "WORSE", "BETTER"],
};

// ---------- saved data (this device only) ----------
export function load(key, fallback) {
  try {
    const v = JSON.parse(localStorage.getItem("obt." + key));
    return v ?? fallback;
  } catch (e) {
    return fallback;
  }
}
export function save(key, value) {
  try {
    localStorage.setItem("obt." + key, JSON.stringify(value));
  } catch (e) { /* private mode / full: keep working without saving */ }
}

// ---------- word prediction ----------
export class Words {
  constructor() {
    this.words = ["HELLO", "HELP", "YES", "NO", "PLEASE", "THANK", "WATER"];
    this.set = new Set(this.words);
    this.counts = load("words", {}) || {};      // word -> times this person used it
    this.pairs = load("pairs", {}) || {};       // "PREV" -> {next: times}
    this.sentences = load("sentences", []) || []; // [[sentence, times], ...] recent last
    this.version = 0;                           // goes up when anything is learned
  }

  async loadList(url = "words.txt") {
    try {
      const text = await (await fetch(url)).text();
      const list = text.split("\n").map((w) => w.trim().toUpperCase()).filter(Boolean);
      if (list.length > 100) {
        this.words = list;
        this.set = new Set(list);
        this.version++;
      }
    } catch (e) { /* offline with no cache: small built-in list still works */ }
  }

  // A learned word is suggested if it's a real word, or a new word (like a
  // name) used at least twice - so one typo doesn't keep popping up.
  trusted(w) {
    return this.set.has(w) || (this.counts[w] || 0) >= 2;
  }

  predict(prefix, n = 3) {
    if (!prefix) return [];
    const out = [];
    const personal = Object.keys(this.counts)
      .filter((w) => w.startsWith(prefix) && w !== prefix && this.trusted(w))
      .sort((a, b) => this.counts[b] - this.counts[a]);
    for (const w of personal) {
      if (!out.includes(w)) out.push(w);
      if (out.length === n) return out;
    }
    for (const w of this.words) {
      if (w.startsWith(prefix) && w !== prefix && !out.includes(w)) {
        out.push(w);
        if (out.length === n) break;
      }
    }
    return out;
  }

  next(prev, n = 3) {
    prev = (prev || "").toUpperCase();
    const learned = Object.entries(this.pairs[prev] || {})
      .filter(([w]) => this.trusted(w))
      .sort((a, b) => b[1] - a[1]).map(([w]) => w);
    const out = [];
    for (const w of [...learned, ...(NEXT_WORDS[prev] || [])]) {
      if (!out.includes(w)) out.push(w);
    }
    return out.slice(0, n);
  }

  learnWord(w) {
    w = (w || "").trim().toUpperCase();
    if (w.length < 2 || !/^[A-Z']+$/.test(w)) return;
    this.counts[w] = (this.counts[w] || 0) + 1;
    this.version++;
    save("words", this.counts);
  }

  learnPair(a, b) {
    a = (a || "").trim().toUpperCase();
    b = (b || "").trim().toUpperCase();
    if (!/^[A-Z']+$/.test(a) || !/^[A-Z']+$/.test(b)) return;
    const d = (this.pairs[a] = this.pairs[a] || {});
    d[b] = (d[b] || 0) + 1;
    this.version++;
    save("pairs", this.pairs);
  }

  learnSentence(text) {
    text = text.toUpperCase().split(/\s+/).filter(Boolean).join(" ");
    if (text.split(" ").length < 2) return;
    const i = this.sentences.findIndex(([s]) => s === text);
    const count = i >= 0 ? this.sentences.splice(i, 1)[0][1] + 1 : 1;
    this.sentences.push([text, count]);        // most recent last
    this.sentences = this.sentences.slice(-50);
    this.version++;
    save("sentences", this.sentences);
  }

  topSentences(n = 3) {
    return this.sentences
      .map(([s, c], i) => [s, c, i])
      .sort((a, b) => b[1] - a[1] || b[2] - a[2])
      .slice(0, n).map(([s]) => s);
  }
}

export function chunks(list, n = 3) {
  const out = [];
  for (let i = 0; i < list.length; i += n) out.push(list.slice(i, i + n));
  return out;
}
