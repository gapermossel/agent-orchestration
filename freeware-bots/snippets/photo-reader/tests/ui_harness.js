// Test harness for the web UI page (GET /). NOT a browser: a tiny stand-in DOM
// that runs the page's own inline <script> under Node, against a running bot.
// It drives the real form handlers (photo upload / message) with real fetch()
// calls to the server and prints what the page would show, as plain text.
// Any use of innerHTML / outerHTML / insertAdjacentHTML / document.write fails the run.
//
// usage: node ui_harness.js BASE_URL photo FILE [CONTENT_TYPE]
//        node ui_harness.js BASE_URL message TEXT
//        node ui_harness.js BASE_URL load
"use strict";
const fs = require("fs");
const path = require("path");

const [base, action, arg, ctype] = process.argv.slice(2);
const htmlTrap = [];

class El {
  constructor(tag, attrs) {
    this.tagName = tag.toUpperCase(); this.attrs = attrs || {}; this.children = []; this.parentNode = null;
    this._text = ""; this.className = this.attrs.class || ""; this.id = this.attrs.id || "";
    this.hidden = "hidden" in this.attrs; this.disabled = false; this.value = ""; this.files = [];
    this.listeners = {}; this.dataset = {}; this.src = "";
    for (const [k, v] of Object.entries(this.attrs)) {
      if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v;
    }
  }
  get textContent() { return this.children.length ? this.children.map(c => c.textContent).join("") : this._text; }
  set textContent(v) { this.children = []; this._text = String(v); }
  get firstChild() { return this.children[0] || null; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; return c; }
  removeAttribute(k) { if (k === "src") this.src = ""; delete this.attrs[k]; }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  dispatch(t) { const ev = { type: t, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
    (this.listeners[t] || []).forEach(fn => fn.call(this, ev)); return ev; }
  set innerHTML(v) { htmlTrap.push("innerHTML set"); throw new Error("innerHTML used"); }
  get innerHTML() { htmlTrap.push("innerHTML read"); throw new Error("innerHTML used"); }
  set outerHTML(v) { htmlTrap.push("outerHTML"); throw new Error("outerHTML used"); }
  insertAdjacentHTML() { htmlTrap.push("insertAdjacentHTML"); throw new Error("insertAdjacentHTML used"); }
}

function attrsOf(s) {
  const a = {}; const re = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:\s*=\s*"([^"]*)")?/g; let m;
  while ((m = re.exec(s))) a[m[1]] = m[2] === undefined ? "" : m[2];
  return a;
}

function dump(node, depth, out) {
  const label = node.tagName.toLowerCase() + (node.id ? "#" + node.id : "") + (node.className ? "." + node.className.split(/\s+/).join(".") : "");
  if (node.children.length) {
    out.push("  ".repeat(depth) + "<" + label + ">");
    node.children.forEach(c => dump(c, depth + 1, out));
  } else {
    out.push("  ".repeat(depth) + "<" + label + "> " + JSON.stringify(node._text));
  }
  return out;
}

async function main() {
  const t0 = Date.now();
  const page = await fetch(base + "/");
  const html = await page.text();
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  if (scripts.length !== 1) throw new Error("expected exactly one inline <script>, got " + scripts.length);
  const ids = {};
  for (const m of html.matchAll(/<([a-z0-9]+)\s([^>]*\bid="[^"]+"[^>]*)>/g)) { const e = new El(m[1], attrsOf(m[2])); ids[e.id] = e; }
  const bodyAttrs = attrsOf((html.match(/<body\s([^>]*)>/) || ["", ""])[1]);
  const requests = [];
  const document = {
    body: new El("body", bodyAttrs),
    getElementById: id => ids[id] || null,
    createElement: t => new El(t),
    write() { htmlTrap.push("document.write"); throw new Error("document.write used"); },
  };
  const realFetch = globalThis.fetch;
  // UI_API_BASE (tests only): send the page's API calls to another server, to
  // simulate a dead bot or a proxy error page. The page itself always comes from BASE_URL.
  const apiBase = process.env.UI_API_BASE || base;
  const fakeFetch = (url, opts) => { requests.push({ method: (opts && opts.method) || "GET", url }); return realFetch(new URL(url, apiBase), opts); };
  const sandboxWindow = { AbortController, document };
  const fn = new Function("window", "document", "fetch", "URL", "setTimeout", "clearTimeout", "setInterval", "clearInterval", scripts[0]);
  fn(sandboxWindow, document, fakeFetch, URL, setTimeout, clearTimeout, setInterval, clearInterval);

  let button = null;
  if (action === "photo") {
    const buf = fs.readFileSync(arg);
    ids["photo-file"].files = [new File([buf], path.basename(arg), { type: ctype || "" })];
    ids["photo-file"].dispatch("change");
    if (!ids["photo-form"].dispatch("submit").defaultPrevented) throw new Error("photo form submit not intercepted");
    button = ids["photo-send"];
  } else if (action === "message") {
    ids["message-text"].value = arg;
    if (!ids["message-form"].dispatch("submit").defaultPrevented) throw new Error("message form submit not intercepted");
    button = ids["message-send"];
  }
  const workingSeen = [];
  if (button) {
    const reply = ids["reply"];
    const sample = () => {
      const first = reply.firstChild;
      if (first && first.className === "working" && workingSeen.length < 3 && !workingSeen.includes(first.textContent)) workingSeen.push(first.textContent);
    };
    sample();   // right after submit, before any reply can arrive
    while (true) {
      await new Promise(r => setTimeout(r, 100));
      sample();
      if (!button.disabled) break;
      if (Date.now() - t0 > 25 * 60 * 1000) throw new Error("harness timeout");
    }
  } else {
    await new Promise(r => setTimeout(r, 1500));
  }
  console.log(JSON.stringify({
    action, requests, working_states_seen: workingSeen, html_api_used: htmlTrap,
    health_line: ids["health"].textContent, reply_card_hidden: ids["reply-card"].hidden,
    preview_shown: !ids["photo-preview"].hidden,
    reply_text_tree: dump(ids["reply"], 0, []),
    harness_elapsed_s: (Date.now() - t0) / 1000,
  }, null, 2));
}
main().catch(e => { console.log(JSON.stringify({ harness_error: String(e && e.stack || e), html_api_used: htmlTrap })); process.exit(1); });
