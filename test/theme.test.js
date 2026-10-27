import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { show } from "../src/frontend/chat.js";

const css = readFileSync(new URL("../src/frontend/theme.css", import.meta.url), "utf8");
const html = readFileSync(new URL("../src/frontend/index.html", import.meta.url), "utf8");

function block(source, opener) {
  const start = source.indexOf(opener);
  assert.notEqual(start, -1, `missing ${opener}`);
  let depth = 0;
  for (let i = source.indexOf("{", start); i < source.length; i++) {
    if (source[i] === "{") depth++;
    if (source[i] === "}" && --depth === 0) return source.slice(source.indexOf("{", start) + 1, i);
  }
  throw new Error(`unclosed ${opener}`);
}

const tokens = (body) => Object.fromEntries([...body.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
const light = tokens(block(css, ":root"));
const dark = { ...light, ...tokens(block(block(css, "@media (prefers-color-scheme: dark)"), ":root")) };

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

test("theme.css defines colour, spacing, radius and font tokens on :root", () => {
  for (const name of ["bg", "surface", "text", "muted", "primary", "primary-text", "callout-bg", "callout-border", "space", "radius", "font"]) {
    assert.ok(name in light, `missing --${name}`);
  }
  assert.equal(light.radius, "8px");
});

test("index.html links theme.css and holds no inline colour values", () => {
  assert.match(html, /<link rel="stylesheet" href="theme\.css">/);
  assert.doesNotMatch(html, /<style|style=|#[0-9a-f]{3,8}\b|rgb\(|hsl\(/i);
});

test("the header names CareConnect with Riverside Health as the sub-line", () => {
  assert.match(html, /<h1>CareConnect<\/h1>/);
  assert.match(html, /Riverside Health/);
});

for (const [mode, t] of [["light", light], ["dark", dark]]) {
  test(`${mode} text and button contrast meets WCAG AA`, () => {
    const pairs = [
      ["text", "bg"], ["text", "surface"], ["muted", "surface"], ["muted", "bg"],
      ["primary-text", "primary"], ["text", "callout-bg"],
    ];
    for (const [fg, bg] of pairs) {
      assert.ok(contrast(t[fg], t[bg]) >= 4.5, `${mode} --${fg} on --${bg}: ${contrast(t[fg], t[bg]).toFixed(2)}`);
    }
  });
}

test("at narrow widths the textarea and Ask button fill the width", () => {
  assert.match(block(css, "#question"), /width:\s*100%/);
  assert.match(block(css, "#question"), /box-sizing:\s*border-box/);
  assert.match(block(css, "button"), /width:\s*100%/);
  assert.match(block(css, "button"), /box-sizing:\s*border-box/);
});

test("the Ask button has a focus ring and a disabled state", () => {
  assert.match(css, /button:focus-visible/);
  assert.match(css, /button:disabled/);
});

test("an escalation reply and a cited reply carry different classes", () => {
  const made = [];
  const doc = { createElement: (tag) => { const e = { tag, children: [], appendChild(c) { this.children.push(c); } }; made.push(e); return e; } };
  const box = { textContent: "", appendChild(c) { (this.children ||= []).push(c); } };
  show(doc, box, { text: "A clinician will follow up.", citations: [], status: "Sent to a clinician for review." });
  assert.equal(box.children[0].className, "status");
  assert.equal(box.children[1].className, "reply-text");
  box.children = [];
  show(doc, box, { text: "Park in lot B.", citations: ["parking.md"] });
  assert.equal(box.children[0].className, "reply-text");
  assert.equal(box.children[1].className, "citations");
  assert.match(css, /\.status\b/);
  assert.match(css, /\.citations\b/);
});

test("the reply region keeps aria-live=polite", () => {
  assert.match(html, /<div id="reply" aria-live="polite">/);
});
