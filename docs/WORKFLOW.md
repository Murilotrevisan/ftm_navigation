# Git Workflow & Agent Rules

> **Binding for every agent.** Violating these is not a style problem; it is a
> process failure. When in doubt, stop and ask rather than proceed.

---

## 1. Branching

The repository is local (`git init`, branch `main`). No remote.

- **`main` is protected by convention.** Never commit directly to `main`.
- **Every feature, phase, or sub-phase gets its own branch:**

```
phase-0/test-infra
phase-1/bench-firmware
phase-2/calibrator-ui
phase-3a/domain-types
phase-3b/domain-core
fix/report-leak-on-failure
```

- Agents working in parallel should use **git worktrees** so they do not fight
  over the working directory:

```bash
git worktree add ../ftm-phase-3b phase-3b/domain-core
```

- Rebase or merge `main` into your branch before requesting review. Do not let
  branches rot.

## 2. The merge gate

**No branch merges into `main` until:**

1. **All tests pass** — every level, not just the ones you touched.
2. **The test results are presented to the human reviewer.**
3. **The human approves the merge.**

Merges are **manual and human-approved**. An agent never merges to `main` on its
own initiative, even if everything is green.

### What "present the results" means

Paste the actual test output. Not a summary claiming it passed — the output.
Include:

- Command run.
- Pass/fail counts per level (L1 host, L2 target, L3 E2E, L4 tools).
- Any skipped tests **and why** they were skipped.
- Duration, so a slow suite is not mistaken for a hang.

If a test failed, say so with the output. Do not describe unverified work as
verified, and do not describe partial work as complete.

## 3. The regression rule

**This is the most important rule in this document.**

An agent implementing a feature will run the whole suite, including tests for
code it did not write and does not use. If a previously passing test now fails:

> **Do not change the test. Change your implementation.**

The test encodes behaviour someone else depends on. A failing pre-existing test
means **your change broke something**, not that the test is wrong.

The only permitted responses:

1. **Fix your implementation** so the existing behaviour is preserved.
2. **Stop and request information** — explain what you are trying to do, which
   test it conflicts with, and why you believe the requirement may have changed.

**Never permitted:** editing, weakening, deleting, skipping, or `xfail`-ing a
pre-existing test to make your change pass. Loosening a tolerance to silence a
failure is the same violation in a more subtle form.

If a test genuinely encodes an obsolete requirement, that is a **human
decision**, made explicitly, in its own commit, with a reason.

## 4. Tests live in `/tests` and are committed

All unit and E2E tests are committed under `tests/`, so that any later agent can
run the entire suite and discover what it broke.

```
tests/
├── host_ceedling/  L1a — Ceedling (Unity/CMock) -> domain/, no hardware
├── host_idf/       L1b — ESP-IDF linux target -> services/, no hardware
├── target/         L2  — on-target Unity test apps
├── e2e/            L3  — pytest-embedded, both boards, autonomous
├── tools/          L4  — pytest for host Python tools
├── sim/            Lsim — simulation (3D logic, N>=4 anchors)
└── manual/         L5  — operator-driven, @pytest.mark.manual
```

Rules:

- **A feature and its tests land in the same commit or the same branch.** Never
  a branch that adds behaviour with tests "to follow".
- Test fixtures use **recorded real data** where the real thing was observed
  (serial transcripts, measured distances). Do not hand-write plausible-looking
  data and present it as a recording.
- Tests must not depend on execution order or on each other's leftovers.

## 5. Commit hygiene

- Present tense, imperative subject: `add rolling median filter`.
- Reference the phase: `phase-3b: add rolling median filter`.
- Body explains **why**, not what — the diff shows what.
- One logical change per commit.
- Never commit `build/`, `sdkconfig`, or generated headers except the
  calibration table, which **is** committed for reproducibility.

### Co-author trailer

Every commit ends with a trailer naming the model that produced it:

```
Co-Authored-By: <Model Name> <noreply@anthropic.com>
```

Use the actual model, e.g. `Claude Opus 4.8`. This makes it possible to
attribute behaviour to a specific model when reviewing history later.

## 6. The work report

**Every phase or feature branch ends with a written report**, committed as
`docs/reports/<branch-name>.md`. The git history records what changed; the
report records *what happened*, which the diff cannot show.

Required sections:

```markdown
# Report — <branch>

## What was built
Plain description of the delivered functionality.

## Deviations from the phase document
Anything done differently from the phase doc, and why.
"None" is a valid answer, but say it explicitly.

## Scope changes
Anything added, dropped, or deferred relative to the original scope.
Include what was NOT done and why.

## Evidence per acceptance criterion
One entry per criterion in the phase document, each with the command run
and its verbatim output. Unticked criteria say what was attempted and what
happened. A criterion with no pasted output is not met.

## Test results
Actual output. Pass/fail counts per level, duration, skips with reasons.

## Blockers encountered
For each: what failed, the diagnostic commands run, their output, and the
root cause. A blocker asserted without diagnostic output is not a blocker.

## New findings
Anything learned about the hardware or toolchain. If HARDWARE_FINDINGS.md
was updated, say what changed.

## Open items
Anything left unresolved, with enough context for the next agent.
```

Rules:

- **Deviations and scope changes are the point of the report.** A report that
  only says "built what was asked, all tests pass" is either wrong or not
  looking hard enough.
- **Every acceptance criterion needs pasted output.** Describing what a file
  contains is not evidence that it works. Code that has never been executed is
  not delivered work (`docs/AGENT_BRIEF.md` §5).
- **A blocker is a claim about the environment, and it gets verified before it
  gets written down** (`docs/AGENT_BRIEF.md` §6). Diagnose the failure; do not
  assume its cause and design around it.
- Report failures and skipped work plainly. Do not describe unverified work as
  verified.
- The report is written **before** requesting review, not after approval.

## 7. What to do when blocked

Stop and ask. Specifically stop — do not:

- Invent a requirement the phase doc does not state.
- Expand scope because something "seemed needed".
- Work around a violated architectural constraint instead of reporting it.
- Fabricate or predict test results you have not seen.

Record the question in your work report (§6).

## 8. Handoff checklist

Before declaring a phase complete:

- [ ] Branch created, work committed to it, `main` untouched.
- [ ] Every acceptance criterion in the phase doc ticked, or explicitly not-done
      with a reason.
- [ ] Full suite run; results pasted in the report.
- [ ] No pre-existing test modified (`git diff main --stat -- tests/` shows only
      additions, or the changes are explained and justified).
- [ ] Phase doc status table updated.
- [ ] `docs/HARDWARE_FINDINGS.md` updated if new measurements were taken.
- [ ] Report written to `docs/reports/<branch-name>.md` (§6).
- [ ] Every commit carries the `Co-Authored-By` model trailer (§5).
- [ ] Open items recorded in the report.
