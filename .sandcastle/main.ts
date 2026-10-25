// Software Factory orchestration for MAOFILHO/AWS-AgentCore-CareConnect-System.
//
// One run = one wave:
//   1. Planner (Opus) reads open issues labelled `factory`, picks the ones that can
//      run now, assigns a branch to each.
//   2. For each issue, in parallel (max 3): one sandbox, one branch.
//        implementer (Sonnet) builds test-first and commits
//        code reviewer (Opus) + security reviewer (Opus) run IN PARALLEL on the same branch,
//          each returning a typed verdict; the implementer fixes CHANGES
//          up to 5 rounds, re-reviewing only the new diff
//        branch is pushed and a PR opened (draft if a reviewer still objects)
//   3. Merging is NOT done here. The factory-merge Action (allow-listed files only) or a human with merge.sh does that.
//
// Everything repo-specific lives in AGENTS.md and the prompt files beside this one.
// Run:  factory run     (or: npx tsx .sandcastle/main.ts)

import * as sandcastle from "@ai-hero/sandcastle";
import { docker } from "@ai-hero/sandcastle/sandboxes/docker";
import { execFileSync } from "node:child_process";
import { z } from "zod";
import { isHumanGate } from "./auto-merge.js";

// ---------------------------------------------------------------------------
// Configuration (overridable with env vars; defaults come from ~/.factory/config)
// ---------------------------------------------------------------------------
const MODELS = {
  planner: process.env.FACTORY_PLANNER_MODEL ?? "claude-opus-5-5",
  builder: process.env.FACTORY_BUILDER_MODEL ?? "claude-sonnet-5-5",
  reviewer: process.env.FACTORY_REVIEWER_MODEL ?? "claude-opus-5-5",
  security: process.env.FACTORY_SECURITY_MODEL ?? "claude-opus-5-5",
};
const MAX_PARALLEL = Number(process.env.FACTORY_MAX_PARALLEL ?? 3);
const MAX_REVIEW_ROUNDS = Number(process.env.FACTORY_MAX_REVIEW_ROUNDS ?? 5);
const MAX_BUILD_ITERATIONS = 40; // implementer loop cap per issue
const REPO = "MAOFILHO/AWS-AgentCore-CareConnect-System";

const hooks = { sandbox: { onSandboxReady: [{ command: "npm ci || npm install", timeoutMs: 300_000 }] } };
const copyToWorktree = ["node_modules"];

// ---------------------------------------------------------------------------
// Schemas for structured agent output
// ---------------------------------------------------------------------------
const planSchema = z.object({
  issues: z.array(z.object({ id: z.string(), title: z.string(), branch: z.string() })),
});

const verdictSchema = z.object({
  verdict: z.enum(["PASS", "CHANGES"]),
  findings: z.array(
    z.object({
      severity: z.enum(["blocker", "major", "minor"]),
      file: z.string(),
      line: z.number().optional(),
      problem: z.string(),
      fix: z.string(),
    }),
  ),
  summary: z.string(),
});
type Verdict = z.infer<typeof verdictSchema>;
type Issue = z.infer<typeof planSchema>["issues"][number];

/** sandbox.run() has no structured-output option in Sandcastle 0.12.x; parse the <review> tag ourselves.
 *  Returns an error string when the reply is missing, is not valid JSON or fails the schema, so the caller can retry. */
function parseVerdict(stdout: string): { ok: true; data: Verdict } | { ok: false; error: string } {
  const m = /<review>([\s\S]*?)<\/review>/.exec(stdout);
  if (!m) return { ok: false, error: "no <review> verdict" };
  const raw = m[1]!.replace(/^```(?:json)?\s*|\s*```$/g, "").trim();
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch (e) {
    return { ok: false, error: `verdict is not valid JSON: ${(e as Error).message}` };
  }
  const parsed = verdictSchema.safeParse(json);
  if (!parsed.success) return { ok: false, error: `verdict failed schema: ${parsed.error.message.slice(0, 200)}` };
  return { ok: true, data: parsed.data };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const gh = (...args: string[]) =>
  execFileSync("gh", args, { encoding: "utf8", stdio: ["ignore", "pipe", "inherit"] }).trim();

const log = (tag: string, msg: string) => console.log(`[${tag}] ${msg}`);

// A human-gate blocker is left for the human merger; it does not fail the security review.
function securityPassed(v: Verdict, changedFiles: string[]): boolean {
  const gate = (f: Verdict["findings"][number]) => isHumanGate(f, changedFiles);
  return v.verdict === "PASS" || (v.findings.some(gate) && v.findings.every((f) => gate(f) || f.severity === "minor"));
}

function renderFindings(name: string, v: Verdict): string {
  if (v.findings.length === 0) return `### ${name}: PASS\n${v.summary}\n`;
  const rows = v.findings
    .map((f) => `- **${f.severity}** \`${f.file}${f.line ? ":" + f.line : ""}\` — ${f.problem} → ${f.fix}`)
    .join("\n");
  return `### ${name}: ${v.verdict}\n${v.summary}\n${rows}\n`;
}

async function withLimit<T>(limit: number, items: readonly T[], fn: (t: T) => Promise<void>): Promise<void> {
  const queue: T[] = [...items];
  const workers = Array.from({ length: Math.min(limit, queue.length) }, async () => {
    while (queue.length) await fn(queue.shift()!);
  });
  await Promise.allSettled(workers);
}

// ---------------------------------------------------------------------------
// Phase 1: Plan
// ---------------------------------------------------------------------------
log("planner", `reading issues labelled 'factory' in ${REPO}`);
// No install hook here: with no branch the planner mounts the host repo, and `npm ci` in the container
// would replace the host node_modules with Linux binaries.
const plan = await sandcastle.run({
  name: "planner",
  sandbox: docker(),
  maxIterations: 1,
  agent: sandcastle.claudeCode(MODELS.planner),
  promptFile: "./.sandcastle/plan-prompt.md",
  output: sandcastle.Output.object({ tag: "plan", schema: planSchema, maxRetries: 1 }),
});

const issues = plan.output.issues;
if (issues.length === 0) {
  log("planner", "no unblocked issues. Nothing to do.");
  process.exit(0);
}
log("planner", `${issues.length} issue(s) this wave, ${MAX_PARALLEL} at a time:`);
for (const i of issues) log("planner", `  #${i.id} ${i.title} → ${i.branch}`);

// ---------------------------------------------------------------------------
// Phase 2: build → (code review ∥ security review) → fix loop → PR
// ---------------------------------------------------------------------------
const results: { id: string; branch: string; pr?: string; state: string }[] = [];

await withLimit(MAX_PARALLEL, issues, async (issue: Issue) => {
  const tag = `#${issue.id}`;
  const sandbox = await sandcastle.createSandbox({ branch: issue.branch, sandbox: docker(), hooks, copyToWorktree });
  try {
    // Build
    // Findings from an earlier failed run, read only from a comment by the factory's own account.
    const me = gh("api", "user", "-q", ".login");
    const prior = gh("issue", "view", issue.id, "--json", "comments", "-q",
      `[.comments[] | select(.author.login == "${me}" and (.body | startswith("Factory: review round")))] | last | .body // ""`);
    log(tag, "implementer starting");
    const build = await sandbox.run({
      name: `implement-${issue.id}`,
      maxIterations: MAX_BUILD_ITERATIONS,
      agent: sandcastle.claudeCode(MODELS.builder),
      promptFile: "./.sandcastle/implement-prompt.md",
      promptArgs: { TASK_ID: issue.id, ISSUE_TITLE: issue.title, BRANCH: issue.branch, PRIOR_FINDINGS: prior },
    });
    if (build.commits.length === 0) {
      log(tag, "no commits produced; labelling needs-human");
      gh("issue", "edit", issue.id, "--add-label", "needs-human");
      gh("issue", "comment", issue.id, "--body", "Factory: the implementer produced no commits. Check the issue is specific enough (acceptance criteria), then remove `needs-human` and re-run.");
      results.push({ id: issue.id, branch: issue.branch, state: "no-commits" });
      return;
    }

    // Review rounds: both reviewers in parallel, same branch, fresh context each round
    let round = 0;
    let code: Verdict | undefined;
    let sec: Verdict | undefined;
    let lastReviewedSha = build.commits.at(-1)!.sha;
    const mergeBase = execFileSync("git", ["merge-base", "HEAD", issue.branch], { encoding: "utf8" }).trim();
    // Files the branch changes; a human-gate blocker only counts for one of these.
    const listChangedFiles = () =>
      execFileSync("git", ["diff", "--name-only", mergeBase, issue.branch], { encoding: "utf8" }).split("\n").filter(Boolean);
    let baseForDiff = mergeBase; // round 1 reviews the whole branch
    while (round < MAX_REVIEW_ROUNDS) {
      round += 1;
      log(tag, `review round ${round}/${MAX_REVIEW_ROUNDS} (code ∥ security)`);
      // A reviewer reply that is not valid JSON gets one retry before it counts as a failed review.
      const review = async (name: string, model: string, file: string): Promise<Verdict> => {
        let error = "";
        for (let attempt = 1; attempt <= 2; attempt++) {
          const r = await sandbox.run({
            name: `${name}-${issue.id}-r${round}${attempt > 1 ? "-retry" : ""}`,
            maxIterations: 1,
            agent: sandcastle.claudeCode(model),
            promptFile: file,
            promptArgs: { TASK_ID: issue.id, BRANCH: issue.branch, DIFF_BASE: baseForDiff, ROUND: String(round) },
          });
          const v = parseVerdict(r.stdout);
          if (v.ok) return v.data;
          error = v.error;
          log(tag, `${name} reply unusable (${error}); ${attempt < 2 ? "retrying once" : "giving up"}`);
        }
        return { verdict: "CHANGES", findings: [{ severity: "major", file: "-", problem: `${name}: ${error}`, fix: "re-run the review" }], summary: "invalid verdict" };
      };
      [code, sec] = await Promise.all([
        review("review", MODELS.reviewer, "./.sandcastle/review-prompt.md"),
        // Stagger the start: two containers writing ~/.gitconfig at once fail with "could not lock config file".
        new Promise((r) => setTimeout(r, 5000)).then(() => review("security", MODELS.security, "./.sandcastle/security-prompt.md")),
      ]);
      const changed = listChangedFiles();
      const blocking = [...code.findings, ...sec.findings].filter((f) => f.severity !== "minor" && !isHumanGate(f, changed));
      if (code.verdict === "PASS" && securityPassed(sec, changed)) break;
      if (round === MAX_REVIEW_ROUNDS) break;

      // Fix: same implementer session style, narrow prompt, only the findings
      log(tag, `${blocking.length} blocking finding(s); implementer fixing`);
      const fix = await sandbox.run({
        name: `fix-${issue.id}-r${round}`,
        maxIterations: 10,
        agent: sandcastle.claudeCode(MODELS.builder),
        prompt: [
          `Address every finding below on branch ${issue.branch}. Make the smallest change that resolves each one.`,
          `Use the diagnosing-bugs skill for findings about wrong behaviour and the implement skill for spec gaps (both in .claude/skills/).`,
          `Run the checks in AGENTS.md before committing. Commit with a one-line message. Do not touch unrelated code.`,
          `When done, output <promise>COMPLETE</promise>.`,
          "",
          renderFindings("Code review", code),
          renderFindings("Security review", sec),
        ].join("\n"),
      });
      if (fix.commits.length > 0) {
        baseForDiff = lastReviewedSha; // next round reviews only the new diff
        lastReviewedSha = fix.commits.at(-1)!.sha;
      }
    }

    // Push + PR. The agent never merges. The factory-merge Action or a human with .sandcastle/merge.sh merges.
    const codeV: Verdict = code ?? { verdict: "CHANGES", findings: [], summary: "not reviewed" };
    const secV: Verdict = sec ?? { verdict: "CHANGES", findings: [], summary: "not reviewed" };
    const changed = listChangedFiles();
    const passed = codeV.verdict === "PASS" && securityPassed(secV, changed);
    const securityBlock = secV.findings.some((f) => f.severity === "blocker" && !isHumanGate(f, changed));
    const body = [
      `Closes #${issue.id}`,
      "",
      "## What changed",
      `_Built by the software factory: ${build.commits.length} commit(s), ${round} review round(s)._`,
      "",
      renderFindings("Code review", codeV),
      renderFindings("Security review", secV),
      securityBlock ? "\n> ⚠️ **Security blocker still open.** Do not merge until resolved." : "",
      "",
      "## Checks",
      "Run by the implementer per AGENTS.md; CI re-runs them on this PR.",
    ].join("\n");

    execFileSync("git", ["push", "-u", "origin", issue.branch, "--force-with-lease"], { stdio: "inherit" });
    // A rerun on an existing branch updates the open PR instead of failing on "already exists".
    let updated = false;
    let prUrl = gh("pr", "list", "--head", issue.branch, "--state", "open", "--json", "url", "-q", ".[0].url // empty");
    if (prUrl) {
      gh("pr", "edit", prUrl, "--body", body);
      // Keep the draft state in step with this run's verdict: factory-merge refuses a draft.
      if (passed) gh("pr", "ready", prUrl);
      else gh("pr", "ready", "--undo", prUrl);
      if (passed && !securityBlock) gh("pr", "edit", prUrl, "--remove-label", "needs-human");
      updated = true;
    } else {
      const prArgs = ["pr", "create", "--head", issue.branch, "--title", `${issue.title} (#${issue.id})`, "--body", body];
      if (!passed) prArgs.push("--draft");
      prUrl = gh(...prArgs);
    }
    // Learn from a failed run: the next implementer reads the issue comments, so the open findings travel with the issue.
    if (!passed) {
      gh("issue", "comment", issue.id, "--body", [
        `Factory: review round ${round} left findings open on ${issue.branch}. The next run must fix these first, on the same branch.`,
        "",
        renderFindings("Code review", codeV),
        renderFindings("Security review", secV),
      ].join("\n"));
    }
    if (securityBlock) gh("pr", "edit", prUrl, "--add-label", "needs-human");
    log(tag, `${passed ? "PR" : "draft PR"} ${updated ? "updated" : "opened"}: ${prUrl}`);
    results.push({ id: issue.id, branch: issue.branch, pr: prUrl, state: passed ? "ready" : "draft" });
  } catch (err) {
    log(tag, `failed: ${(err as Error).message}`);
    results.push({ id: issue.id, branch: issue.branch, state: "error" });
  } finally {
    await sandbox.close();
  }
});

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------
console.log("\nWave complete");
for (const r of results) console.log(`  #${r.id}  ${r.state.padEnd(10)} ${r.pr ?? r.branch}`);
console.log("\nNext: review the PRs, approve, merge. Run again when new 'factory' issues exist.");
