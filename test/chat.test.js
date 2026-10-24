import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  ask, show, init, ESCALATION_NOTICE, BLOCK_NOTICE, ERROR_NOTICE,
} from "../src/frontend/chat.js";

const apiUrl = "https://api.test/careconnect";
const fakeApi = (status, body) => async () => ({ ok: status < 400, status, json: async () => body });

function el() {
  const e = { children: [], textContent: "", listeners: {} };
  e.appendChild = (c) => { e.children.push(c); };
  e.addEventListener = (n, f) => { e.listeners[n] = f; };
  return e;
}

test("a reply shows its text and citation names", async () => {
  const fetch = fakeApi(200, { decision: "allow", reply: "Park in lot B.", citations: ["parking.md"] });
  const result = await ask("Where do I park?", { apiUrl, fetch });
  assert.deepEqual(result, { text: "Park in lot B.", citations: ["parking.md"] });
  const doc = { createElement: el };
  const box = el();
  show(doc, box, result);
  assert.equal(box.children[0].textContent, "Park in lot B.");
  assert.equal(box.children[1].children[0].textContent, "parking.md");
});

test("an escalation shows only the fixed notice", async () => {
  const fetch = fakeApi(200, { decision: "escalate", reply: "secret draft", citations: ["a.md"] });
  assert.deepEqual(await ask("q", { apiUrl, fetch }), { text: ESCALATION_NOTICE, citations: [] });
});

test("a block shows no draft text", async () => {
  const fetch = fakeApi(200, { decision: "block", reply: "draft text", citations: ["a.md"] });
  assert.deepEqual(await ask("q", { apiUrl, fetch }), { text: BLOCK_NOTICE, citations: [] });
});

test("an API error shows one fixed message with no error text", async () => {
  const expected = { text: ERROR_NOTICE, citations: [] };
  assert.deepEqual(await ask("q", { apiUrl, fetch: fakeApi(500, { error: "boom trace" }) }), expected);
  const down = async () => { throw new Error("network boom"); };
  assert.deepEqual(await ask("q", { apiUrl, fetch: down }), expected);
});

test("the page never writes the patient's text to console or storage", async () => {
  const secret = "my chest hurts SECRET";
  const seen = [];
  const methods = ["log", "info", "warn", "error", "debug"];
  const saved = methods.map((m) => console[m]);
  methods.forEach((m) => { console[m] = (...a) => seen.push(a.join(" ")); });
  const storage = { setItem: (k, v) => seen.push(k + v) };
  const prev = { localStorage: globalThis.localStorage, sessionStorage: globalThis.sessionStorage };
  globalThis.localStorage = storage;
  globalThis.sessionStorage = storage;
  try {
    const form = el(), input = el(), box = el();
    input.value = secret;
    const doc = { createElement: el, getElementById: (id) => ({ "chat-form": form, question: input, reply: box })[id] };
    init(doc, { apiUrl, fetch: fakeApi(500, {}) });
    await form.listeners.submit({ preventDefault() {} });
  } finally {
    methods.forEach((m, i) => { console[m] = saved[i]; });
    globalThis.localStorage = prev.localStorage;
    globalThis.sessionStorage = prev.sessionStorage;
  }
  assert.deepEqual(seen, []);
  const src = readFileSync(new URL("../src/frontend/chat.js", import.meta.url), "utf8");
  assert.doesNotMatch(src, /console\.|localStorage|sessionStorage|document\.cookie/);
});
