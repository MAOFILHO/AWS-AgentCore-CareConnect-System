import { REQUIRED_CHECKS } from "./auto-merge.js";

// What the factory does next with one PR. No human question: wait, merge, send back to build, or stop after the attempt cap.
/**
 * @param {{ checks: { name: string, bucket: string }[], attempts: number, maxAttempts: number, draft: boolean, needsHuman: boolean }} s
 * @returns {{ action: "wait" | "merge" | "rebuild" | "stop", reason: string }}
 */
export function nextStep({ checks, attempts, maxAttempts, draft, needsHuman }) {
  if (needsHuman) return { action: "stop", reason: "PR has the needs-human label" };
  const bucket = (n) => checks.find((c) => c.name === n)?.bucket;
  if (REQUIRED_CHECKS.some((n) => bucket(n) === undefined || bucket(n) === "pending")) return { action: "wait", reason: "checks still running" };
  const failed = REQUIRED_CHECKS.filter((n) => bucket(n) !== "pass");
  if (failed.length === 0 && !draft) return { action: "merge", reason: "all required checks pass" };
  const reason = failed.length ? `failed: ${failed.join(", ")}` : "PR is a draft";
  return attempts >= maxAttempts ? { action: "stop", reason: `${reason}; ${attempts} attempts used` } : { action: "rebuild", reason };
}

// Written on the issue so the next build reads it through prior-findings.js.
export const findingsComment = (pr, branch, findings) =>
  `Factory: review round ${pr} left findings open on ${branch} (checks of PR #${pr}). Fix these first, on the same branch.\n\n${findings}`;
