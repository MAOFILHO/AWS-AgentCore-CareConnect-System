import { test } from "node:test";
import assert from "node:assert/strict";
import { nextStep, findingsComment } from "../.sandcastle/drive-policy.js";

const REQ = ["tests-typecheck-lint", "semgrep", "gitleaks", "ai-code-review", "ai-security-review"];
const all = (bucket) => REQ.map((name) => ({ name, bucket }));
const base = { checks: all("pass"), attempts: 1, maxAttempts: 3, draft: false, needsHuman: false };

test("all green merges", () => assert.equal(nextStep(base).action, "merge"));

test("pending check waits", () => {
  const checks = [...all("pass").slice(1), { name: REQ[0], bucket: "pending" }];
  assert.equal(nextStep({ ...base, checks }).action, "wait");
});

test("missing check waits", () => assert.equal(nextStep({ ...base, checks: all("pass").slice(1) }).action, "wait"));

test("failed review under the cap goes back to build", () => {
  const checks = all("pass").map((c) => (c.name === "ai-code-review" ? { ...c, bucket: "fail" } : c));
  assert.equal(nextStep({ ...base, checks }).action, "rebuild");
});

test("failed review at the cap stops", () => {
  const checks = all("fail");
  assert.equal(nextStep({ ...base, checks, attempts: 3 }).action, "stop");
});

test("needs-human or draft never merges", () => {
  assert.equal(nextStep({ ...base, needsHuman: true }).action, "stop");
  assert.equal(nextStep({ ...base, draft: true }).action, "rebuild");
});

test("findings comment starts with the prior-findings marker", () => {
  assert.match(findingsComment(87, "sandcastle/issue-86", "body"), /^Factory: review round/);
});
