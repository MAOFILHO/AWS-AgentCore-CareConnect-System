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

test("promote fails closed: no ignored failures, and the PR job waits for the checks", () => {
  assert.doesNotMatch(workflow, /continue-on-error|\|\| true|always\(\)/);
  assert.match(workflow, /open-pr:\n(?: {4}.*\n)*? {4}needs: checks\n/);
});

test("promote opens one staging to main PR and never pushes", () => {
  assert.doesNotMatch(workflow, /git push|contents: write/);
  assert.equal(workflow.match(/gh pr create/g).length, 1);
  assert.match(workflow, /gh pr create [^\n]*--base main --head staging/);
});
