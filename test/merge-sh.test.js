import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const SHA = "0123456789abcdef0123456789abcdef01234567";
const script = new URL("../.sandcastle/merge.sh", import.meta.url).pathname;

function runMerge({ mergeFails = false } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "merge-sh-"));
  const log = join(dir, "calls.log");
  const gh = `#!/usr/bin/env bash
echo "$*" >> "${log}"
case "$1 $2" in
  "pr view") printf 'sandcastle/issue-1\\tfalse\\tfalse\\t${SHA}\\n' ;;
  "pr checks") printf 'test\\tpass\\t1m\\n' ;;
  "pr merge") ${mergeFails ? "echo 'head commit mismatch' >&2; exit 1" : "exit 0"} ;;
esac
`;
  writeFileSync(join(dir, "gh"), gh);
  chmodSync(join(dir, "gh"), 0o755);
  const r = spawnSync("bash", [script, "7"], {
    encoding: "utf8",
    env: { ...process.env, PATH: `${dir}:${process.env.PATH}` },
  });
  return { ...r, calls: readFileSync(log, "utf8").trim().split("\n") };
}

test("merge.sh merges only the head commit it read", () => {
  const r = runMerge();
  assert.equal(r.status, 0);
  assert.ok(r.calls.includes(`pr merge 7 --merge --match-head-commit ${SHA}`), r.calls.join("\n"));
  assert.match(r.stdout, /merged PR #7/);
});

test("merge.sh fails and prints no merged line when GitHub refuses the merge", () => {
  const r = runMerge({ mergeFails: true });
  assert.notEqual(r.status, 0);
  assert.doesNotMatch(r.stdout, /merged PR/);
});
