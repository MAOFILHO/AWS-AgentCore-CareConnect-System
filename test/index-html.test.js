import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("index.html sets a mobile viewport", () => {
  const html = readFileSync(new URL("../src/frontend/index.html", import.meta.url), "utf8");
  assert.match(
    html,
    /<meta name="viewport" content="width=device-width, initial-scale=1">/,
  );
});
