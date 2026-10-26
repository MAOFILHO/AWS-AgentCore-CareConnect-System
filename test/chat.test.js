import { test, mock } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  ask, show, init, ERROR_NOTICE, REQUEST_TIMEOUT_MS,
} from "../src/frontend/chat.js";

const ESCALATION_NOTICE = "A licensed clinician will follow up with you.";
const ESCALATE = "Sent to a clinician for review.";
const STOPPED = "We could not answer this. Please contact the hospital.";
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

test("an escalation shows the server's notice and no citations", async () => {
  const fetch = fakeApi(200, { decision: "escalate", reply: ESCALATION_NOTICE, citations: ["a.md"] });
  assert.deepEqual(await ask("q", { apiUrl, fetch }), { text: ESCALATION_NOTICE, citations: [], status: ESCALATE });
});

test("a block shows the server's reply and no citations", async () => {
  const fetch = fakeApi(200, { decision: "block", reply: "The assistant cannot help with that.", citations: ["a.md"] });
  assert.deepEqual(await ask("q", { apiUrl, fetch }), { text: "The assistant cannot help with that.", citations: [], status: STOPPED });
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

const FAILED_ESCALATION = "We could not pass your request to a clinician. Please contact Riverside Health directly, or call emergency services if your symptoms are urgent.";

test("a failed escalation shows the server's call-us reply, not a promise", async () => {
  const fetch = fakeApi(200, { decision: "escalate", reply: FAILED_ESCALATION, citations: [] });
  assert.deepEqual(await ask("q", { apiUrl, fetch }), { text: FAILED_ESCALATION, citations: [], status: ESCALATE });
});

test("a budget stop shows the server's reply", async () => {
  const reply = "This request is taking too long, so I stopped. Please try again or call us.";
  const fetch = fakeApi(200, { decision: "stop", reply, citations: [] });
  assert.deepEqual(await ask("q", { apiUrl, fetch }), { text: reply, citations: [], status: STOPPED });
});

test("a malformed 200 body shows the error notice", async () => {
  const expected = { text: ERROR_NOTICE, citations: [] };
  for (const body of [{}, { decision: "allow" }, { decision: "escalate" }, { decision: "other", reply: "x" }, { decision: ["escalate"], reply: "x" }, { decision: ["block"], reply: "x" }, null]) {
    assert.deepEqual(await ask("q", { apiUrl, fetch: fakeApi(200, body) }), expected, JSON.stringify(body));
  }
});

test("an answer without citations or with bad citations shows only valid names", async () => {
  const fetch = (citations) => fakeApi(200, { decision: "allow", reply: "No approved answer.", citations });
  assert.deepEqual(await ask("q", { apiUrl, fetch: fetch(undefined) }), { text: "No approved answer.", citations: [] });
  assert.deepEqual(await ask("q", { apiUrl, fetch: fetch(["a.md", 7, null]) }), { text: "No approved answer.", citations: ["a.md"] });
});

test("show() renders the status above the reply text with textContent", () => {
  const doc = { createElement: el };
  const box = el();
  show(doc, box, { text: "<b>x</b>", citations: [], status: ESCALATE });
  assert.equal(box.children.length, 2);
  assert.equal(box.children[0].textContent, ESCALATE);
  assert.equal(box.children[1].textContent, "<b>x</b>");
  const plain = el();
  show(doc, plain, { text: "ok", citations: [] });
  assert.equal(plain.children.length, 1);
  const stopped = el();
  show(doc, stopped, { text: "r", citations: [], status: STOPPED });
  assert.equal(stopped.children[0].textContent, STOPPED);
});

test("each of the 4 decisions gives the right status", async () => {
  const expected = { allow: undefined, escalate: ESCALATE, block: STOPPED, stop: STOPPED };
  for (const [decision, status] of Object.entries(expected)) {
    const result = await ask("q", { apiUrl, fetch: fakeApi(200, { decision, reply: "r", citations: [] }) });
    assert.equal(result.status, status, decision);
    assert.equal("status" in result, status !== undefined, decision);
  }
  assert.equal("status" in await ask("q", { apiUrl, fetch: fakeApi(500, {}) }), false);
});

const AWAITING = "Awaiting clinician approval.";

test("a staged reply shows the awaiting-approval status; false or missing shows none", async () => {
  const body = { decision: "allow", reply: "Staged.", citations: [] };
  assert.equal((await ask("q", { apiUrl, fetch: fakeApi(200, { ...body, staged: true }) })).status, AWAITING);
  for (const staged of [false, undefined, "true", 1]) {
    const result = await ask("q", { apiUrl, fetch: fakeApi(200, { ...body, staged }) });
    assert.equal("status" in result, false, String(staged));
  }
  const esc = await ask("q", { apiUrl, fetch: fakeApi(200, { decision: "escalate", reply: "r", staged: true }) });
  assert.equal(esc.status, ESCALATE);
  const box = el();
  show({ createElement: el }, box, { text: "<b>x</b>", citations: [], status: AWAITING });
  assert.equal(box.children[0].textContent, AWAITING);
});

const hangs = (_url, { signal }) => new Promise((_, reject) => {
  signal.addEventListener("abort", () => reject(new Error("aborted")));
});

test("a request that never answers aborts after the timeout and shows the error", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const pending = ask("q", { apiUrl, fetch: hangs });
    mock.timers.tick(REQUEST_TIMEOUT_MS - 1);
    let settled = false;
    pending.then(() => { settled = true; });
    await new Promise((r) => setImmediate(r));
    assert.equal(settled, false);
    mock.timers.tick(1);
    assert.deepEqual(await pending, { text: ERROR_NOTICE, citations: [] });
  } finally {
    mock.timers.reset();
  }
});

test("the timeout is 35 seconds", () => {
  assert.equal(REQUEST_TIMEOUT_MS, 35_000);
});

test("a reply in time is unchanged and clears the timer", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const fetch = fakeApi(200, { decision: "allow", reply: "Park in lot B.", citations: ["parking.md"] });
    let signal;
    const result = await ask("q", { apiUrl, fetch: (u, init) => { signal = init.signal; return fetch(u, init); } });
    assert.deepEqual(result, { text: "Park in lot B.", citations: ["parking.md"] });
    mock.timers.tick(REQUEST_TIMEOUT_MS);
    assert.equal(signal.aborted, false);
  } finally {
    mock.timers.reset();
  }
});
