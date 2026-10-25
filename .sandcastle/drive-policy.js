import { REQUIRED_CHECKS, PROTECTED } from "./auto-merge.js";

// Files that judge or steer the factory itself. The factory never merges a PR that changes one: a human does.
const CONTROL = [".sandcastle/", ".github/", ".claude/", "Docs/adr/", "AGENTS.md", "CLAUDE.md", "REVIEW.md",
  "infra/", "Docs/Repo/careconnect-approved-docs/", "test/drive-policy.test.js", "test/merge-sh.test.js", "test/prior-findings.test.js", "package.json", "package-lock.json", "requirements.txt", ".semgrep.yml", "eslint.config.js", "tsconfig.json"];
// Every protected test judges the code it sits beside, so any change to one waits for a human, even an added line (a new @skip weakens a test too).
// The list is auto-merge.js PROTECTED, so the two merge paths cannot drift.
const isProtectedTest = (f) => PROTECTED.includes(f) && (f.startsWith("test/"));
/** @param {string[]} files */
export const touchesControl = (files) => files.some((f) => CONTROL.some((c) => (c.endsWith("/") ? f.startsWith(c) : f === c)) || isProtectedTest(f));

// Paths a PR changes, from the paginated REST files list. A rename counts its old path too.
export const changedPaths = (apiFiles) => apiFiles.flatMap((f) => [f.filename, f.previous_filename].filter(Boolean));

// What the factory does next with one PR. No human question: wait, merge, send back to build, or stop after the attempt cap.
/**
 * @param {{ checks: { name: string, bucket: string }[], attempts: number, maxAttempts: number, draft: boolean, needsHuman: boolean, files: string[] }} s
 * @returns {{ action: "wait" | "merge" | "hold" | "rebuild" | "stop", reason: string }}
 */
export function nextStep({ checks, attempts, maxAttempts, draft, needsHuman, files }) {
  if (needsHuman) return { action: "stop", reason: "PR has the needs-human label" };
  const bucket = (n) => checks.find((c) => c.name === n)?.bucket;
  if (REQUIRED_CHECKS.some((n) => bucket(n) === undefined) || checks.some((c) => c.bucket === "pending")) return { action: "wait", reason: "checks still running" };
  const failed = REQUIRED_CHECKS.filter((n) => bucket(n) !== "pass");
  if (failed.length === 0 && !draft && touchesControl(files)) return { action: "hold", reason: "PR changes factory control files; a human merges it" };
  if (failed.length === 0 && !draft) return { action: "merge", reason: "all required checks pass" };
  const reason = failed.length ? `failed: ${failed.join(", ")}` : "PR is a draft";
  return attempts >= maxAttempts ? { action: "stop", reason: `${reason}; ${attempts} attempts used` } : { action: "rebuild", reason };
}

// Written on the issue so the next build reads it through prior-findings.js.
export const findingsComment = (round, pr, branch, findings) =>
  `Factory: drive attempt ${round} (PR #${pr}) left findings open on ${branch}. Fix these first, on the same branch.\n\n${findings}`;

// Only the factory's own drive comments count; in-container review rounds do not.
export const countDriveAttempts = (comments, me) =>
  comments.filter((c) => c.author?.login === me && (c.body ?? "").startsWith("Factory: drive attempt")).length;

// The CI review text that travels back to the builder: only the Actions bot may write it, so no commenter can plant a prompt.
export const trustedReview = (comments) =>
  comments.filter((c) => c.author?.login === "github-actions" && (c.body ?? "").includes("<!-- factory-review -->")).at(-1)?.body ?? "";

// Quality rule: the model that reviews must not be the model that built. Checked once, before any container starts.
export function assertIndependentReviewers(builder, reviewer, security) {
  if (reviewer === builder) throw new Error(`reviewer model ${reviewer} is the builder model; set FACTORY_REVIEWER_MODEL to a different model`);
  if (security === builder) throw new Error(`security model ${security} is the builder model; set FACTORY_SECURITY_MODEL to a different model`);
}
