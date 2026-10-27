export const WAITING_NOTICE = "Looking this up\u2026";
export const NOT_CONNECTED_NOTICE = "This site is not connected yet. Please contact the hospital.";
export const ERROR_NOTICE = "Something went wrong. Please try again.";
const ESCALATE_STATUS = "Sent to a clinician for review.";
const STOPPED_STATUS = "We could not answer this. Please contact the hospital.";
const AWAITING_STATUS = "Awaiting clinician approval.";
// Supervisor limit (30 s) plus 5 s margin.
export const REQUEST_TIMEOUT_MS = 35_000;
const STATUS = { escalate: ESCALATE_STATUS, block: STOPPED_STATUS, stop: STOPPED_STATUS };

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
      return { text: body.reply, citations: [], status: STATUS[body.decision] };
    }
    if (body.decision === "allow" && typeof body.reply === "string") {
      const citations = Array.isArray(body.citations) ? body.citations.filter((c) => typeof c === "string") : [];
      return body.staged === true
        ? { text: body.reply, citations, status: AWAITING_STATUS }
        : { text: body.reply, citations };
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
    for (const name of citations) {
      const li = doc.createElement("li");
      li.textContent = name;
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
