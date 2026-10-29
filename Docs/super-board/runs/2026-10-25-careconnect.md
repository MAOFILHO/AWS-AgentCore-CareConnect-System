# careconnect runs

| card | lanes | final | column | detail |
|---|---|---|---|---|
| #100 | build → qa → review | merged | Done | PR #103; gate first failed on PEP 668 pip, merged via venv |
| #101 | preflight | blocked | Blocked | same file as #100; returns to Ready after #100 closes |
| #102 | build → qa → review | merged | Done | PR #104; gate first failed on draft state, run halted, halt archived after remote check |
| #101 | build → qa → review | blocked | Blocked | PR #105 reviewed clean; gate stalled on PEP 668; merge awaits owner |
| #101 | build → qa → review | merged | Done | PR #105 merged via gate after #106 venv fix |
| #107 | build → qa → review | merged | Done | PR #111, no findings |
| #108 | build → qa → review | merged | Done | PR #112, no findings |
| #109 | preflight | blocked | Blocked | external PR #110 claims it (does not fix it); needs owner to close #110 |
| #109 | build → qa → review | merged | Done | PR #114 (f42e5fc) to staging, truth-check 90 |
| #93 | build → qa → review | merged | Done | PR #118 via gate; first halt: reviewer skipped gh pr ready (prompt fixed) |
| #94 | build → qa → review | blocked | Ready | PR #117 409 lines over the 400 cap; sent back to Build to trim |
| #94 | build → qa → review | merged | Done | PR #117 (8921fbb) after trim to 255 lines |
| #95 | build → qa → review | merged | Done | PR #119 (c373532), truth-check 85; follow-ups R1 R2 |
| #120 | build → qa → review | merged | Done | PR #121 (3d94ab8), no findings |
| #96 | build → qa → review | blocked | Ready | PR #122 475 lines over cap; split: gateway stays, deploy-runtime.sh moves to new ticket |
| #96 | build → qa → review | merged | Done | PR #122 (e37de5d) after split to 348 lines; deploy script moved to #123 |
| #123 | build → qa → review | merged | Done | PR #124 (af78d88), no findings |
| #97 | IaC 5a/5 API stack template | PR #126 | merged 948cb62 on staging | rebuilt once for size (600 > 400, QA logs) |
| #125 | IaC 5b/5 deploy.sh and teardown.sh | PR #127 | merged 13e99e0 on staging | 1 review bounce (R1-R4), 1 size split (wizard removal to #129) |
| #115 | README run test deploy | PR #132 | merged cf9ff77 on staging | clean |
| #116 | smoke test script | PR #131 | merged 4ec0a13 on staging | clean |
| #129 | remove deploy-wizard.sh | PR #130 | merged on staging | pure deletion 478 lines, over size cap; supervisor merged |
| 2026-10-26 | #133 | PR #138 | merged 4155d10 | halt on bad gh call (--slurp with --jq), resumed at QA |
| 2026-10-26 | #135 | PR #140 | merged 539c618 | R1 open: shipped prices total 0.035 max, cap cannot trip |
| 2026-10-26 | #134 | PR #139 | QA bounce 1 | suicide and overdose phrases still allowed; 4 goldens pass with pattern removed |
| 2026-10-26 | #136 | PR #143 | merged 3cdaaa4 | clean |
| 2026-10-26 | #134 | PR #139 | QA bounce 2 | self-harming inflection allowed; stem matching ordered |
| 2026-10-26 | #137 | PR #142 | QA bounce 1 | GITHUB_TOKEN cannot open PR (repo setting); workflow to emit compare URL instead |
| 2026-10-26 | #141 | PR #144 | merged 5807ee5 | clean |
| 2026-10-26 | #134 | PR #139 | merged 86593ca (supervisor ran gh pr ready and the gate after the lane agent was denied) | 2 QA bounces, 14 goldens mutation-checked |
| 2026-10-26 | #137 | PR #142 | rebuild pushed f727485; lane denied note refresh; moved to QA | compare URL instead of PR create |
| 2026-10-26 | #137 | PR #142 | merged 136ae70 | clean after 1 QA bounce |
| 2026-10-26 | #145 | PR #148 | merged f86138f | clean; #146 and #147 blocked on #145 (shared fakes.py) |
| 2026-10-26 | #146 | PR #149 | merged 055f681 | halt on wrong repo slug in agent gh call; prompt now pins slug |
| 2026-10-26 | #147 | PR #150 | merged 9b5cfc7 | clean; non-blocking R1: verify() forwarding of safety/guardrail not asserted |
| 2026-10-26 | #152 | PR #153 | merged 35dbfe7 | 1 bounce (requirements missing mcp-proxy-for-aws, import path unproven) |
| 2026-10-26 | #154 | PR #155 | merged b8ce15e | clean; nit R1 |
| 2026-10-26 | #156 | PR #157 | merged d6f2757 | clean; runtime role scoped permissions |
| #158 | PR #159 | 5b631b1 | Done | runtime model ID -> Haiku 4.5 |
| #160 | PR #161 | a609727 | Done | log error_type on supervisor failure |
| #163 | PR #165 | 2505252 | Done | scratch files to /tmp |
| #162 | PR #164 | - | Blocked | gh pr ready denied by classifier |
| #166 | PR #167 | f504db3 | Done | runtime role lambda:InvokeFunction |
| #168 | PR #170 | 36a0543 | Done | safety gate drug names |
| #169 | PR #171 | - | Ready (bounced r1) | relevance check |
| #169 | Verification passes answers that do not address the question | review:advanced | PR #171 merged 8c747c1 (round 2) |
| #172 | Question field too small | preflight:blocked-by-overlap-note | not built, back in Ready |
| #172 | Question field too small | review:advanced | PR #173 merged 43b2711 |
| #174 | Answers repeat whole document | review:human-gate (round 2 clean) | PR #175 held: protected test_golden.py, merge.sh refuses branch name |
| #176 | PR #177 4ffeafb | merged by owner instruction; smoke FAIL on visiting hours, rolled back |
| #179 | PR #180 3b657ce | build>qa>review no findings; deployed, smoke PASS |
| #178 | PR #181 4eaa678 | build>qa>review no blockers; deployed, smoke PASS, 9/9 medication probes escalate |
| #182 | closed not planned | PR 183 closed; Guardrail anonymizes PHONE, safe miss, owner decision needed to allow listed hospital numbers |
| #184 | merged PR 186 e26c2eb | Safety gate Lambda patterns aligned with src; parity test + golden |
| #185 | frontend: apply the Contoso theme to the chat page | merged PR 187 (0c67d9b) after 1 rebuild |
| #188 | stop false clinician status | bounced r1 (PR 190) |
| #189 | Lambda urgent patterns | bounced r1 (PR 192) |
| #188 | stop false clinician status | merged PR 190 (2f9fdec) after 1 rebuild |
| #189 | Lambda urgent patterns | merged PR 192 (b0bc71f) after 2 rebuilds |
| #191 | readable citations | merged PR 193 (26049b1) |
| #195 | smoke probes (approved source, urgent, block) | merged PR 197 (0847d47) after 1 rebuild |
| #196 | failure notices as alerts, named reply region | merged PR 198 (b061602) after 1 rebuild |
| #200 | Verification fails closed on malformed Safety Lambda reply | merged PR 201 (4ef06c2) |
| #202 | failed Task/Tool call escalates, no placeholder in reply | merged PR 203 (b1e7f39) after 1 rebuild |
| 205 | PR 206 | 1d638e9 | rebuild 1 (log level Gap), truth 90/100 |
| 212 | PR 213 | 1910dd6 | QA bounce (golden test), rebuild 2 (smoke digits), truth 85/100 |
| 214 | PR 215 | b37d1e2 | review round 1, no findings, truth 72/100 |
| 216 | PR 217 | 8c09890 | review round 1, no findings, truth 78/100 |
