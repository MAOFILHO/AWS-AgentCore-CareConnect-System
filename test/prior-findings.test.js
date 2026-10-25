import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { priorFindings } from "../.sandcastle/prior-findings.js";

const c = (body, login = "bot") => ({ author: { login }, body });

test("pass after fail gives empty prior", () => {
  assert.equal(priorFindings([c("Factory: review round 2 left findings open"), c("Factory: review passed")], "bot"), "");
});

test("fail with no later pass gives the findings", () => {
  const f = "Factory: review round 3 left findings open";
  assert.equal(priorFindings([c("Factory: review passed"), c("Factory: review round 1 x"), c(f), c("hi")], "bot"), f);
});

test("ignores other authors and no comments", () => {
  assert.equal(priorFindings([c("Factory: review round 1 x", "someone")], "bot"), "");
  assert.equal(priorFindings([], "bot"), "");
});

test("factory-improve still reads only review round comments", () => {
  const y = readFileSync(new URL("../.github/workflows/factory-improve.yml", import.meta.url), "utf8");
  assert.match(y, /startswith\("Factory: review round"\)/);
});
