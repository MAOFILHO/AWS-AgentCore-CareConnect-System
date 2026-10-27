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

test("index.html uses a multi-line textarea for the question", () => {
  const html = readFileSync(new URL("../src/frontend/index.html", import.meta.url), "utf8");
  const tag = html.match(/<textarea\b[^>]*>/);
  assert.ok(tag, "textarea present");
  assert.match(tag[0], /\bid="question"/);
  assert.match(tag[0], /\brequired\b/);
  assert.ok(Number(tag[0].match(/\brows="(\d+)"/)?.[1]) >= 4, "rows >= 4");
  assert.doesNotMatch(html, /<input\b[^>]*id="question"/);
});
