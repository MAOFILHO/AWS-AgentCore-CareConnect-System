import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const yml = read("../.github/workflows/factory-merge.yml");
const rules = read("../.sandcastle/auto-merge.js");

test("workflow matches the protected-file and allow-list reasons that auto-merge.js returns", () => {
  assert.ok(rules.includes("reason: `PR touches protected file ${hit}`"));
  assert.ok(rules.includes("reason: `${outside} is not on the allow list`"));
  assert.ok(yml.includes('"$reason" == "PR touches protected file"*'));
  assert.ok(yml.includes('"$reason" == *" is not on the allow list"'));
});

test("workflow does not label for the non-final reasons", () => {
  const branch = yml.split("elif [[")[1].split("then")[0];
  for (const r of ["switched off", "draft", "has not passed", "label"]) assert.ok(!branch.includes(r));
});
