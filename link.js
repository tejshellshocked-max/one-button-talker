// One-Button Talker - Caregiver Link (patient <-> caregiver's phone).
//
// Works anywhere (Wi-Fi or cellular) through ntfy.sh, a free public message
// relay. Everything is END-TO-END ENCRYPTED with AES-GCM in the browser: the
// secret key lives only in the link's "#k=..." part, which browsers never send
// to any server. The relay only ever sees scrambled bytes, and the channel
// name is a one-way hash of the key, so it can't be guessed.

const RELAY = globalThis.TALKER_RELAY || "https://ntfy.sh/";   // tests can point this at a local relay

function b64url(bytes) {
  let s = "";
  bytes.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function unb64url(str) {
  const s = atob(str.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

export function newKey() {
  return b64url(crypto.getRandomValues(new Uint8Array(16)));
}

export class Link {
  static async open(key) {
    const raw = unb64url(key);
    if (raw.length !== 16) throw new Error("bad link key");
    const cryptoKey = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256",
      new TextEncoder().encode("one-button-talker:" + key)));
    const id = [...digest.slice(0, 10)].map((b) => b.toString(16).padStart(2, "0")).join("");
    return new Link(key, cryptoKey, id);
  }

  constructor(key, cryptoKey, id) {
    this.key = key;
    this.cryptoKey = cryptoKey;
    this.id = id;
    this.seen = new Set();
    this.sources = [];
    this.connected = false;
  }

  topic(side) {          // "p" patient events, "c" caregiver commands, "a" plain alerts
    return "obt" + this.id + side;
  }
  alertTopic() {
    return this.topic("a");
  }

  caregiverUrl() {
    return new URL("caregiver.html", location.href).href.split("#")[0] + "#k=" + this.key;
  }

  async encrypt(obj) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const data = new TextEncoder().encode(JSON.stringify(obj));
    const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, this.cryptoKey, data));
    const out = new Uint8Array(12 + ct.length);
    out.set(iv);
    out.set(ct, 12);
    return b64url(out);
  }

  async decrypt(text) {
    const raw = unb64url(text);
    const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: raw.slice(0, 12) }, this.cryptoKey, raw.slice(12));
    return JSON.parse(new TextDecoder().decode(pt));
  }

  async send(side, obj) {
    try {
      const body = await this.encrypt(obj);
      const r = await fetch(RELAY + this.topic(side), { method: "POST", body });
      return r.ok;
    } catch (e) {
      return false;
    }
  }

  // A plain push for the ntfy phone app (works even when the phone is locked).
  // It says nothing private - just that help is needed.
  async sendAlertPush() {
    try {
      const q = "?title=" + encodeURIComponent("One-Button Talker") + "&priority=urgent&tags=rotating_light";
      await fetch(RELAY + this.alertTopic() + q,
        { method: "POST", body: "Help alert - open the caregiver page now" });
    } catch (e) { /* the in-page alert still works */ }
  }

  // Receive messages. since: "all" (history) or a unix time in seconds.
  listen(side, since, onMessage) {
    const es = new EventSource(RELAY + this.topic(side) + "/sse?since=" + since);
    es.onopen = () => (this.connected = true);
    es.onerror = () => (this.connected = false);
    es.onmessage = async (ev) => {
      let m;
      try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m.event !== "message" || !m.message || this.seen.has(m.id)) return;
      this.seen.add(m.id);
      try {
        const obj = await this.decrypt(m.message);
        obj._time = m.time;
        onMessage(obj);
      } catch (e) { /* not ours / tampered: ignore */ }
    };
    this.sources.push(es);
    return es;
  }

  close() {
    this.sources.forEach((s) => s.close());
    this.sources = [];
  }
}
