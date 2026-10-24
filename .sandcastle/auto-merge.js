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

// The factory merges only files that match here. A new file in any other place needs a human,
// so a file this list forgot to protect fails closed.
const ALLOWED = [/^src\/frontend\/[^.][^/]*(\/[^/]+)*$/, /^test\/[^/]+\.test\.js$/, /^(README|GLOSSARY)\.md$/];

const isAllowed = (file) => !file.includes("..") && ALLOWED.some((re) => re.test(file));

const isProtected = (file) => PROTECTED.some((p) => (p.endsWith("/") ? file.startsWith(p) : file === p));

// A protected-path blocker whose only fix is "human review required" never clears: a human merges those PRs anyway.
// The fix must be that phrase alone (any case, optional trailing period), the one .sandcastle/security-prompt.md tells the reviewer to write; keep them in sync.
export const isHumanGate = (finding) =>
  finding.severity === "blocker" && isProtected(finding.file) && /^\s*human review required\.?\s*$/i.test(finding.fix);

export function decide({ enabled, crossRepository, branch, draft, labels, checks, files, changedFiles }) {
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
  if (changedFiles > 100) return { merge: false, reason: `PR has ${changedFiles} changed files` };
  const hit = files.find(isProtected);
  if (hit) return { merge: false, reason: `PR touches protected file ${hit}` };
  const outside = files.find((f) => !isAllowed(f));
  if (outside) return { merge: false, reason: `${outside} is not on the allow list` };
  return { merge: true, reason: "all checks pass" };
}
