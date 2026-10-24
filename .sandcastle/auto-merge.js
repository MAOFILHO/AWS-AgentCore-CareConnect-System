// Checks a PR must pass before the factory merges it. A check that is missing counts as not passed.
export const REQUIRED_CHECKS = [
  "tests-typecheck-lint", "semgrep", "gitleaks", "ai-code-review", "ai-security-review",
];

// Files a human must merge: patient-safety code, the release gate, dependencies, workflows and approved documents.
// A prefix ends in "/". Edit this list to widen or narrow what the factory may merge on its own.
export const PROTECTED = [
  "src/careconnect/agents/", "src/careconnect/safety_gate.py", "src/careconnect/supervisor.py",
  "src/careconnect/supervisor_model.py", "src/careconnect/verification.py", "src/careconnect/gateway.py",
  "src/careconnect/budget.py", "src/careconnect/config.json", "src/careconnect/document_processing.py",
  "src/careconnect/ingest.py", "test/test_golden.py", "test/test_safety_gate.py",
  ".github/", ".sandcastle/", ".claude/", "infra/", "Docs/adr/", "Docs/Repo/lambda-functions/",
  "Docs/Repo/careconnect-approved-docs/", "AGENTS.md", "REVIEW.md",
  "package.json", "package-lock.json", "requirements.txt",
  // Configs of the checks themselves: a PR must not weaken the gate it is judged by.
  ".semgrep.yml", "eslint.config.js", "tsconfig.json", "CLAUDE.md",
  "test/test_untrusted_documents.py", "src/careconnect/model.json", "src/careconnect/fakes.py",
  "test/test_logging.py", "test/test_verification.py", "test/test_supervisor.py", "test/test_gateway.py",
  "test/test_supervisor_agent.py", "test/test_proxy_lambda.py", "test/test_agents_import.py",
  "test/auto-merge.test.js",
];

const isProtected = (file) => PROTECTED.some((p) => (p.endsWith("/") ? file.startsWith(p) : file === p));

export function decide({ enabled, crossRepository, branch, draft, labels, checks, files }) {
  if (!enabled) return { merge: false, reason: "auto-merge is switched off" };
  if (crossRepository) return { merge: false, reason: "PR comes from a fork" };
  if (!branch.startsWith("sandcastle/")) return { merge: false, reason: "not a factory branch" };
  if (draft) return { merge: false, reason: "PR is a draft" };
  for (const label of ["needs-human", "protected-paths"]) {
    if (labels.includes(label)) return { merge: false, reason: `PR has the ${label} label` };
  }
  for (const name of REQUIRED_CHECKS) {
    if (checks.find((c) => c.name === name)?.bucket !== "pass") {
      return { merge: false, reason: `check ${name} has not passed` };
    }
  }
  const hit = files.find(isProtected);
  if (hit) return { merge: false, reason: `PR touches protected file ${hit}` };
  return { merge: true, reason: "all checks pass" };
}
