import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const workflow = readFileSync(new URL("../.github/workflows/factory-improve.yml", import.meta.url), "utf8");

test("factory-improve gives Claude Read and Edit only, never Write", () => {
  const tools = [...workflow.matchAll(/--allowedTools "([^"]*)"/g)].map((m) => m[1]);
  assert.deepEqual(tools, ["Read,Edit"]);
});
