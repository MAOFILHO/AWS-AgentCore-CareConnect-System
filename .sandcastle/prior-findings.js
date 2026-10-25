// Findings the next run must fix: the last "Factory: review" comment from the
// factory account, if it is a failed round. A later pass clears them.
/**
 * @param {{ author?: { login?: string }, body?: string }[]} comments oldest first
 * @param {string} me
 * @returns {string}
 */
export function priorFindings(comments, me) {
  const last = comments
    .filter((c) => c.author?.login === me && (c.body ?? "").startsWith("Factory: review"))
    .at(-1);
  const body = last?.body ?? "";
  return body.startsWith("Factory: review round") ? body : "";
}
