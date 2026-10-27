import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const script = fileURLToPath(new URL("../scripts/smoke.sh", import.meta.url));
const REPLY_TEXT = "Visiting hours are 11:00 to 20:00.";

const answer = (id, body) => `HTTP/2 200\r\nx-amzn-RequestId: ${id}\r\n\r\n${JSON.stringify(body)}`;
const cited = answer("req-1", { decision: "allow", reply: REPLY_TEXT, citations: ["s3://bucket/approved/visiting-hours-and-policy.md"], staged: false });
const uncited = answer("req-1", { decision: "allow", reply: REPLY_TEXT, citations: [], staged: false });
const escalated = answer("req-2", { decision: "escalate", reply: "A clinician will review this.", citations: [], staged: false });
const answered = answer("req-2", { decision: "allow", reply: "Take two.", citations: ["a.md"], staged: false });
const wrongSource = answer("req-1", { decision: "allow", reply: REPLY_TEXT, citations: ["s3://bucket/evaluation-untrusted/doc.md"], staged: false });
const blocked = answer("req-4", { decision: "block", reply: "Blocked.", citations: [], staged: false });

// A fake curl on PATH answers each probe by its prompt: routine, clinical, urgent and manipulation.
// Probes a test does not name get the reply a healthy deploy gives.
function run(args, { routine = cited, clinical = escalated, urgent = escalated, manipulation = blocked, curlFails = false } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "smoke-sh-"));
  for (const [name, reply] of Object.entries({ routine, clinical, urgent, manipulation })) {
    writeFileSync(join(dir, `${name}.txt`), reply);
  }
  const curl = `#!/usr/bin/env bash
${curlFails ? "exit 7" : ""}
case "$*" in
  *visiting*) cat "${dir}/routine.txt" ;;
  *breathe*) cat "${dir}/urgent.txt" ;;
  *"Ignore previous"*) cat "${dir}/manipulation.txt" ;;
  *) cat "${dir}/clinical.txt" ;;
esac
`;
  writeFileSync(join(dir, "curl"), curl);
  chmodSync(join(dir, "curl"), 0o755);
  return spawnSync("bash", [script, ...args], {
    encoding: "utf8",
    env: { ...process.env, PATH: `${dir}:${process.env.PATH}` },
  });
}

test("smoke.sh exits non-zero when the API URL is empty", () => {
  assert.notEqual(run([""], { routine: cited, clinical: escalated }).status, 0);
  assert.notEqual(run([], { routine: cited, clinical: escalated }).status, 0);
});

test("smoke.sh exits 0 for a cited answer and an escalation, and prints ids and decisions only", () => {
  const r = run(["https://api.example.com/careconnect"], { routine: cited, clinical: escalated });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /routine: PASS request_id=req-1 decision=allow/);
  assert.match(r.stdout, /clinical: PASS request_id=req-2 decision=escalate/);
  assert.match(r.stdout, /urgent: PASS request_id=req-2 decision=escalate/);
  assert.match(r.stdout, /manipulation: PASS request_id=req-4 decision=block/);
  assert.ok(!(r.stdout + r.stderr).includes(REPLY_TEXT));
  const out = (r.stdout + r.stderr).toLowerCase();
  for (const text of ["ibuprofen", "breathe", "ignore previous"]) assert.ok(!out.includes(text));
});

test("smoke.sh fails when the routine answer has no citation", () => {
  const r = run(["https://api.example.com"], { routine: uncited, clinical: escalated });
  assert.equal(r.status, 1);
  assert.match(r.stdout, /routine: FAIL/);
});

test("smoke.sh fails when the routine citation is not an approved source", () => {
  const r = run(["https://api.example.com"], { routine: wrongSource });
  assert.equal(r.status, 1);
  assert.match(r.stdout, /routine: FAIL/);
});

test("smoke.sh fails when the urgent-only probe is answered", () => {
  const r = run(["https://api.example.com"], { urgent: answered });
  assert.equal(r.status, 1);
  assert.match(r.stdout, /urgent: FAIL/);
});

test("smoke.sh fails when the manipulation probe is allowed", () => {
  const r = run(["https://api.example.com"], { manipulation: answered });
  assert.equal(r.status, 1);
  assert.match(r.stdout, /manipulation: FAIL/);
});

test("smoke.sh fails when the clinical question is answered", () => {
  const r = run(["https://api.example.com"], { routine: cited, clinical: answered });
  assert.equal(r.status, 1);
  assert.match(r.stdout, /clinical: FAIL/);
});

test("smoke.sh fails on a non-JSON reply and on a failed request", () => {
  assert.equal(run(["https://api.example.com"], { routine: "HTTP/2 500\r\n\r\nnope", clinical: escalated }).status, 1);
  assert.equal(run(["https://api.example.com"], { curlFails: true }).status, 1);
});
