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

test("index.html names the reply region and does not make it an alert", () => {
  const html = readFileSync(new URL("../src/frontend/index.html", import.meta.url), "utf8");
  const tag = html.match(/<div\b[^>]*id="reply"[^>]*>/);
  assert.ok(tag, "reply region present");
  assert.match(tag[0], /\baria-label="[^"]+"/);
  assert.doesNotMatch(tag[0], /role="alert"/);
});

test("index.html caps the question at 2000 characters", () => {
  const html = readFileSync(new URL("../src/frontend/index.html", import.meta.url), "utf8");
  const tag = html.match(/<textarea\b[^>]*>/);
  assert.match(tag[0], /\bmaxlength="2000"/);
});
