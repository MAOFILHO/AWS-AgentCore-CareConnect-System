import { test } from "node:test";
import assert from "node:assert/strict";
import { greet } from "../src/index.js";

test("greet returns a greeting", () => {
  assert.equal(greet("factory"), "Hello, factory!");
});
