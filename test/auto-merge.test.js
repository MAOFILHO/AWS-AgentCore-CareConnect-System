import { test } from "node:test";
import assert from "node:assert/strict";
import { decide } from "../.sandcastle/auto-merge.js";

const REQUIRED = ["tests-typecheck-lint", "semgrep", "gitleaks", "ai-code-review", "ai-security-review"];
const green = REQUIRED.map((name) => ({ name, bucket: "pass" }));
const ok = {
  enabled: true, crossRepository: false, branch: "sandcastle/issue-7", draft: false, labels: [],
  checks: green, files: ["src/frontend/chat.js", "test/chat.test.js"],
};

test("a green, ordinary factory PR merges", () => {
  assert.deepEqual(decide(ok), { merge: true, reason: "all checks pass" });
});

const refused = (change, expectedReason) => {
  const out = decide({ ...ok, ...change });
  assert.equal(out.merge, false);
  assert.match(out.reason, expectedReason);
};

test("it never merges while the kill switch is off", () => refused({ enabled: false }, /switched off/));
test("it never merges a non-factory branch", () => refused({ branch: "main-fix" }, /not a factory branch/));
test("it never merges a draft", () => refused({ draft: true }, /draft/));
test("it never merges a needs-human PR", () => refused({ labels: ["needs-human"] }, /needs-human/));
test("it never merges a protected-paths PR", () => refused({ labels: ["protected-paths"] }, /protected-paths/));

test("it never merges while a required check is failing, pending or missing", () => {
  for (const bucket of ["fail", "pending", "skipping", "cancel"]) {
    const checks = green.map((c) => (c.name === "semgrep" ? { ...c, bucket } : c));
    refused({ checks }, /semgrep/);
  }
  refused({ checks: green.filter((c) => c.name !== "ai-security-review") }, /ai-security-review/);
  refused({ checks: [] }, /tests-typecheck-lint/);
});

test("it never merges a PR that touches safety, workflow, dependency or approved-document files", () => {
  const protectedFiles = [
    "src/careconnect/safety_gate.py", "src/careconnect/supervisor.py", "src/careconnect/verification.py",
    "src/careconnect/gateway.py", "src/careconnect/budget.py", "src/careconnect/agents/escalation_agent.py",
    "src/careconnect/agents/supervisor_agent.py", "src/careconnect/agents/verification_agent.py",
    "test/test_golden.py", "test/test_safety_gate.py", ".github/workflows/factory-ci.yml",
    ".sandcastle/auto-merge.js", "AGENTS.md", "REVIEW.md", "package.json", "requirements.txt",
    "Docs/adr/0001-factory-aws-access-capped-account.md", "infra/factory-account.yaml",
    "Docs/Repo/careconnect-approved-docs/approved/visiting-hours-and-policy.md",
    "Docs/Repo/lambda-functions/careconnect-deterministic-safety/lambda_function.py",
    ".semgrep.yml", "eslint.config.js", "tsconfig.json", "CLAUDE.md",
    "test/test_untrusted_documents.py", "src/careconnect/model.json",
  ];
  for (const file of protectedFiles) {
    refused({ files: ["src/frontend/chat.js", file] }, new RegExp(file.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("it never merges a PR from a fork, even with a factory branch name", () => {
  refused({ crossRepository: true }, /fork/);
});
