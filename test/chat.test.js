import { test, mock } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  ask, show, init, ERROR_NOTICE, REQUEST_TIMEOUT_MS, WAITING_NOTICE, NOT_CONNECTED_NOTICE,
} from "../src/frontend/chat.js";

const ESCALATION_NOTICE = "A licensed clinician will follow up with you.";
const ESCALATE = "Sent to a clinician for review.";
const STOPPED = "We could not answer this. Please contact the hospital.";
const apiUrl = "https://api.test/careconnect";
const fakeApi = (status, body) => async () => ({ ok: status < 400, status, json: async () => body });

function el() {
  let text = "";
  const e = { children: [], listeners: {} };
  Object.defineProperty(e, "textContent", { get: () => text, set: (v) => { text = v; if (v === "") e.children = []; } });
  e.appendChild = (c) => { e.children.push(c); };
  e.addEventListener = (n, f) => { e.listeners[n] = f; };
  return e;
}

test("a reply shows its text and citation names", async () => {
  const fetch = fakeApi(200, { decision: "allow", reply: "Park in lot B.", citations: ["parking.md"] });
  const result = await ask("Where do I park?", { apiUrl, fetch });
  assert.deepEqual(result, { text: "Park in lot B.", citations: [{ name: "Parking", uri: "parking.md" }] });
  const doc = { createElement: el };
  const box = el();
  show(doc, box, result);
  assert.equal(box.children[0].textContent, "Park in lot B.");
  assert.equal(box.children[1].children[0].textContent, "Parking");
  assert.equal(box.children[1].children[0].title, "parking.md");
});

const VISITING_URI = "s3://careconnect-approved-docs-759316130780-us-east-1/approved/visiting-hours-and-policy.md";

test("an allow reply hides its Source sentence and names the citation readably", async () => {
  const fetch = fakeApi(200, { decision: "allow", reply: `Visiting is 9 to 5. Source: ${VISITING_URI}`, citations: [VISITING_URI] });
  const result = await ask("q", { apiUrl, fetch });
  assert.equal(result.text, "Visiting is 9 to 5.");
  assert.deepEqual(result.citations, [{ name: "Visiting hours and policy", uri: VISITING_URI }]);
  const box = el();
  show({ createElement: el }, box, result);
  assert.equal(box.children[1].children[0].textContent, "Visiting hours and policy");
  assert.equal(box.children[1].children[0].title, VISITING_URI);
  assert.equal(box.children.some((c) => c.textContent.includes("s3://")), false);
});

test("the ticket sentence shows a short reference and no status words", async () => {
  const reply = "Your medication question requires review by a licensed clinician. (Ticket: 6d0c72c7-3a98-4785-b664-7d64a2c5ab79, status: pending_review)";
  const result = await ask("q", { apiUrl, fetch: fakeApi(200, { decision: "escalate", reply, citations: [] }) });
  assert.equal(result.text, "Your medication question requires review by a licensed clinician. (Reference: 6d0c72c7)");
  assert.equal(result.text.includes("pending_review"), false);
});

test("a reply with neither pattern is shown unchanged", async () => {
  const reply = "Source of parking: lot B.\nTicket office opens at 9.";
  const result = await ask("q", { apiUrl, fetch: fakeApi(200, { decision: "allow", reply, citations: [] }) });
  assert.equal(result.text, reply);
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

test("the failed-escalation text matches the notice in supervisor.py", () => {
  const py = readFileSync(new URL("../src/careconnect/supervisor.py", import.meta.url), "utf8");
  const block = py.match(/ESCALATION_FAILED_NOTICE = \(([^)]*)\)/)[1];
  const notice = [...block.matchAll(/"([^"]*)"/g)].map((m) => m[1]).join("");
  assert.equal(FAILED_ESCALATION, notice);
});

test("a failed escalation shows the server's call-us reply with no clinician status", async () => {
  const fetch = fakeApi(200, { decision: "escalate", reply: FAILED_ESCALATION, citations: [] });
  assert.deepEqual(await ask("q", { apiUrl, fetch }), { text: FAILED_ESCALATION, citations: [] });
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
  assert.deepEqual(await ask("q", { apiUrl, fetch: fetch(["a.md", 7, null]) }), { text: "No approved answer.", citations: [{ name: "A", uri: "a.md" }] });
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
    assert.deepEqual(result, { text: "Park in lot B.", citations: [{ name: "Parking", uri: "parking.md" }] });
    mock.timers.tick(REQUEST_TIMEOUT_MS);
    assert.equal(signal.aborted, false);
  } finally {
    mock.timers.reset();
  }
});

function chatPage(fetch) {
  const form = el(), input = el(), box = el();
  const doc = { createElement: el, getElementById: (id) => ({ "chat-form": form, question: input, reply: box })[id] };
  init(doc, { apiUrl, fetch });
  const submit = (q) => { input.value = q; return form.listeners.submit({ preventDefault() {} }); };
  return { box, submit };
}

test("a second submit while one is pending sends no second request", async () => {
  let calls = 0;
  let release;
  const fetch = () => { calls += 1; return new Promise((r) => { release = r; }); };
  const { box, submit } = chatPage(fetch);
  const first = submit("one");
  await submit("two");
  assert.equal(calls, 1);
  release({ ok: true, json: async () => ({ decision: "allow", reply: "first answer", citations: [] }) });
  await first;
  assert.equal(box.children[0].textContent, "first answer");
});

test("after a reply or an error the next submit works", async () => {
  const replies = [fakeApi(500, {}), fakeApi(200, { decision: "allow", reply: "ok", citations: [] })];
  let calls = 0;
  const { box, submit } = chatPage((...a) => replies[calls++](...a));
  await submit("one");
  assert.equal(box.children[0].textContent, ERROR_NOTICE);
  await submit("two");
  assert.equal(calls, 2);
  assert.equal(box.children.at(-1).textContent, "ok");
});

test("the waiting text shows after submit and the reply replaces it", async () => {
  let release;
  const { box, submit } = chatPage(() => new Promise((r) => { release = r; }));
  const first = submit("one");
  assert.equal(box.textContent, "");
  assert.equal(box.children.at(-1).textContent, WAITING_NOTICE);
  assert.equal(WAITING_NOTICE, "Looking this up\u2026");
  release({ ok: true, json: async () => ({ decision: "allow", reply: "the answer", citations: [] }) });
  await first;
  assert.deepEqual(box.children.map((c) => c.textContent), ["the answer"]);
});

test("the fixed error replaces the waiting text", async () => {
  const { box, submit } = chatPage(fakeApi(500, {}));
  await submit("one");
  assert.deepEqual(box.children.map((c) => c.textContent), [ERROR_NOTICE]);
});

test("an empty question shows no waiting text", async () => {
  const { box, submit } = chatPage(fakeApi(200, {}));
  await submit("   ");
  assert.equal(box.children.length, 0);
});

test("the placeholder API URL shows the not-connected text and never calls fetch", async () => {
  let calls = 0;
  const form = el(), input = el(), box = el();
  const doc = { createElement: el, getElementById: (id) => ({ "chat-form": form, question: input, reply: box })[id] };
  init(doc, { apiUrl: "https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/prod/careconnect", fetch: () => { calls += 1; } });
  input.value = "when is the clinic open";
  await form.listeners.submit({ preventDefault() {} });
  assert.equal(calls, 0);
  assert.equal(NOT_CONNECTED_NOTICE, "This site is not connected yet. Please contact the hospital.");
  assert.deepEqual(box.children.map((c) => c.textContent), [NOT_CONNECTED_NOTICE]);
});

test("a real API URL still calls fetch", async () => {
  let calls = 0;
  const { submit } = chatPage(() => { calls += 1; return fakeApi(500, {})(); });
  await submit("one");
  assert.equal(calls, 1);
});
