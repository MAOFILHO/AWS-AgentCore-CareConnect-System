export const WAITING_NOTICE = "Looking this up\u2026";
export const NOT_CONNECTED_NOTICE = "This site is not connected yet. Please contact the hospital.";
export const ERROR_NOTICE = "Something went wrong. Please try again.";
const ESCALATE_STATUS = "Sent to a clinician for review.";
const STOPPED_STATUS = "We could not answer this. Please contact the hospital.";
const AWAITING_STATUS = "Awaiting clinician approval.";
// Same text as ESCALATION_FAILED_NOTICE in src/careconnect/supervisor.py.
const ESCALATION_FAILED_NOTICE = "We could not pass your request to a clinician. Please contact Riverside Health directly, or call emergency services if your symptoms are urgent.";
// Supervisor limit (30 s) plus 5 s margin.
export const REQUEST_TIMEOUT_MS = 35_000;
const STATUS = { escalate: ESCALATE_STATUS, block: STOPPED_STATUS, stop: STOPPED_STATUS };

// Show a document name a patient can read: file name only, no extension, hyphens as spaces.
function citationName(uri) {
  const file = uri.slice(uri.lastIndexOf("/") + 1).replace(/\.[^.]*$/, "").replace(/-/g, " ");
  return file ? file[0].toUpperCase() + file.slice(1) : uri;
}

// Drop the backend's trailing "Source: <uri>" sentence and shorten the ticket sentence.
// Text that matches neither pattern is returned unchanged.
function readableReply(reply) {
  return reply
    .replace(/(?:\s*Source:\s*\S+)+\s*$/, "")
    .replace(/\(Ticket: ([^\s,)]{1,8})[^\s,)]*, status: [a-z_]+\)/g, "(Reference: $1)");
}

// Turn the API reply into what the page shows. Anything unexpected is the fixed error.
export async function ask(question, { apiUrl, fetch }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: question }),
      signal: controller.signal,
    });
    if (!res.ok) return { text: ERROR_NOTICE, citations: [] };
    const body = await res.json();
    if (typeof body.decision === "string" && Object.hasOwn(STATUS, body.decision) &&typeof body.reply === "string") {
      const text = readableReply(body.reply);
      return body.reply === ESCALATION_FAILED_NOTICE
        ? { text, citations: [] }
        : { text, citations: [], status: STATUS[body.decision] };
    }
    if (body.decision === "allow" && typeof body.reply === "string") {
      const citations = Array.isArray(body.citations)
        ? body.citations.filter((c) => typeof c === "string").map((uri) => ({ name: citationName(uri), uri }))
        : [];
      const text = readableReply(body.reply);
      return body.staged === true
        ? { text, citations, status: AWAITING_STATUS }
        : { text, citations };
    }
  } catch {
    // fall through to the fixed error
  } finally {
    clearTimeout(timer);
  }
  return { text: ERROR_NOTICE, citations: [] };
}

// Show a result with textContent only, so reply text is never parsed as HTML.
export function show(doc, container, { text, citations, status }) {
  container.textContent = "";
  if (status) {
    const s = doc.createElement("p");
    s.className = "status";
    s.textContent = status;
    container.appendChild(s);
  }
  const p = doc.createElement("p");
  p.className = "reply-text";
  p.textContent = text;
  container.appendChild(p);
  if (citations.length) {
    const ul = doc.createElement("ul");
    ul.className = "citations";
    for (const { name, uri } of citations) {
      const li = doc.createElement("li");
      li.textContent = name;
      li.title = uri;
      ul.appendChild(li);
    }
    container.appendChild(ul);
  }
}

export function init(doc, { apiUrl, fetch }) {
  const form = doc.getElementById("chat-form");
  const input = doc.getElementById("question");
  const container = doc.getElementById("reply");
  let pending = false;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question || pending) return;
    if (apiUrl.includes("YOUR-API-ID")) {
      show(doc, container, { text: NOT_CONNECTED_NOTICE, citations: [] });
      return;
    }
    pending = true;
    try {
      show(doc, container, { text: WAITING_NOTICE, citations: [] });
      show(doc, container, await ask(question, { apiUrl, fetch }));
    } finally {
      pending = false;
    }
  });
}

if (typeof document !== "undefined") {
  init(document, { apiUrl: window.CARECONNECT_CONFIG.API_URL, fetch: window.fetch.bind(window) });
}
