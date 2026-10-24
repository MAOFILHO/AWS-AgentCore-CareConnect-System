export const ESCALATION_NOTICE = "A licensed clinician will follow up with you.";
export const BLOCK_NOTICE = "I can't help with that request.";
export const ERROR_NOTICE = "Something went wrong. Please try again.";

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
    if (body.decision === "escalate") return { text: ESCALATION_NOTICE, citations: [] };
    if (body.decision === "block") return { text: BLOCK_NOTICE, citations: [] };
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
export function show(doc, container, { text, citations }) {
  container.textContent = "";
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
