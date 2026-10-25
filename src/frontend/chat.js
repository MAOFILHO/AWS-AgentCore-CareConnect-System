export const ERROR_NOTICE = "Something went wrong. Please try again.";
const ESCALATE_STATUS = "Sent to a clinician for review.";
const STOPPED_STATUS = "We could not answer this. Please contact the hospital.";
const STATUS = { escalate: ESCALATE_STATUS, block: STOPPED_STATUS, stop: STOPPED_STATUS };

// Turn the API reply into what the page shows. Anything unexpected is the fixed error.
export async function ask(question, { apiUrl, fetch }) {
  try {
    const res = await fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: question }),
    });
    if (!res.ok) return { text: ERROR_NOTICE, citations: [] };
    const body = await res.json();
    if (Object.hasOwn(STATUS, body.decision) && typeof body.reply === "string") {
      return { text: body.reply, citations: [], status: STATUS[body.decision] };
    }
    if (body.decision === "allow" && typeof body.reply === "string") {
      const citations = Array.isArray(body.citations) ? body.citations.filter((c) => typeof c === "string") : [];
      return { text: body.reply, citations };
    }
  } catch {
    // fall through to the fixed error
  }
  return { text: ERROR_NOTICE, citations: [] };
}

// Show a result with textContent only, so reply text is never parsed as HTML.
export function show(doc, container, { text, citations, status }) {
  container.textContent = "";
  if (status) {
    const s = doc.createElement("p");
    s.textContent = status;
    container.appendChild(s);
  }
  const p = doc.createElement("p");
  p.textContent = text;
  container.appendChild(p);
  if (citations.length) {
    const ul = doc.createElement("ul");
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
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    show(doc, container, await ask(question, { apiUrl, fetch }));
  });
}

if (typeof document !== "undefined") {
  init(document, { apiUrl: window.CARECONNECT_CONFIG.API_URL, fetch: window.fetch.bind(window) });
}
