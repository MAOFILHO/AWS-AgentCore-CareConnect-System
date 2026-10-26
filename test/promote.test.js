import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const workflow = read("../.github/workflows/promote.yml");
const agents = read("../AGENTS.md");

// Returns the indented lines under a top-level YAML key, up to the next top-level key.
const block = (key) => {
  const lines = workflow.split("\n");
  const start = lines.indexOf(`${key}:`);
  assert.notEqual(start, -1, `no top-level ${key}: in promote.yml`);
  const end = lines.findIndex((l, i) => i > start && /^\S/.test(l));
  return lines.slice(start + 1, end === -1 ? undefined : end).filter((l) => l.trim());
};

test("promote runs only when started by hand", () => {
  assert.deepEqual(block("on"), ["  workflow_dispatch:"]);
});

test("promote runs every check listed in AGENTS.md", () => {
  const checks = agents.split("## Checks")[1].split("```bash\n")[1].split("```")[0].trim().split("\n");
  assert.ok(checks.length >= 5);
  for (const cmd of checks) assert.ok(workflow.includes(`- run: ${cmd}\n`), `missing check: ${cmd}`);
});

test("promote fails closed: no ignored failures, and the handoff job waits for the checks", () => {
  assert.doesNotMatch(workflow, /continue-on-error|\|\| true|always\(\)/);
  assert.match(workflow, /handoff:\n(?: {4}.*\n)*? {4}needs: checks\n/);
});

test("promote writes the compare URL for the checked staging commit to the job summary", () => {
  assert.match(workflow, /COMPARE_URL: [^\n]*\/compare\/main\.\.\.\$\{\{ needs\.checks\.outputs\.sha \}\}\n/);
  assert.match(workflow, /echo "Compare: \$COMPARE_URL"\n(?:.*\n)*? *\} >> "\$GITHUB_STEP_SUMMARY"\n/);
});

test("promote never pushes, never opens a PR and needs no write permission", () => {
  assert.doesNotMatch(workflow, /git push|gh pr create|gh api|: write/);
});
