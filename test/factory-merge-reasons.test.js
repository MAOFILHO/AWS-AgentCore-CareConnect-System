import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { decide, REQUIRED_CHECKS as REQUIRED } from "../.sandcastle/auto-merge.js";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const yml = read("../.github/workflows/factory-merge.yml");
const rules = read("../.sandcastle/auto-merge.js");

test("workflow matches the protected-file and allow-list reasons that auto-merge.js returns", () => {
  assert.ok(rules.includes("reason: `PR touches protected file ${hit}`"));
  assert.ok(rules.includes("reason: `${outside} is not on the allow list`"));
  assert.ok(yml.includes('"$reason" == "PR touches protected file"*'));
  assert.ok(yml.includes('"$reason" == *" is not on the allow list"'));
});

test("workflow labels only the protected-file and allow-list reasons", () => {
  const labels = (reason) => reason.startsWith("PR touches protected file") || reason.endsWith(" is not on the allow list");
  const base = { enabled: true, crossRepository: false, branch: "sandcastle/issue-1", draft: false, labels: [], changedFiles: 1, files: ["x"], checks: REQUIRED.map((name) => ({ name, bucket: "pass" })) };
  const cases = [
    [{ enabled: false }, false], [{ crossRepository: true }, false], [{ branch: "main" }, false], [{ draft: true }, false],
    [{ labels: ["needs-human"] }, false], [{ labels: ["protected-paths"] }, false], [{ checks: [] }, false],
    [{ changedFiles: 101 }, false], [{ files: [".github/workflows/x.yml"] }, true], [{ files: ["package.json"] }, true],
  ];
  for (const [change, expected] of cases) assert.equal(labels(decide({ ...base, ...change }).reason), expected, JSON.stringify(change));
  assert.equal(yml.split("elif [[").length, 2);
  assert.ok(!yml.includes("else\n"));
});
