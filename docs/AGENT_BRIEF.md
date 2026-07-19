# Agent Brief

**Read this before starting any phase.** Every phase document links here. It is
the same for all of them; only the phase document differs.

---

## 1. Required reading, in order

1. `docs/AGENT_BRIEF.md` — this file
2. `docs/PLAN.md` — goal, current state, constraints
3. `docs/HARDWARE_FINDINGS.md` — **normative measured facts**
4. `docs/WORKFLOW.md` — branching, merge gate, regression rule, report
5. `docs/CONTAINER.md` — where builds and tests run
6. Your own phase document, in full

Read anything else only if your phase document points at it. Do not read other
phase documents "for context" — they will pull you off-scope.

## 2. Work in a worktree, on a branch

Never work on `main`. Never commit to `main`.

```bash
git worktree add ../ftm-<phase> -b <phase-branch>
cd ../ftm-<phase>
```

The exact branch name is in your phase document. Worktrees let phases run in
parallel without fighting over the working directory.

**Every file you create or edit lives inside your worktree.** Do not put some
files there and others in the main checkout — split work is unreviewable and
half of it will be lost. Before requesting review:

```bash
git -C <path-to-main-checkout> status --short   # must be clean
git log main..HEAD --oneline                    # must be non-empty
```

**Commit as you go.** An uncommitted worktree is not deliverable work: it
carries no message, no co-author trailer, and nothing for the reviewer to diff.

## 3. Environment

Builds and host unit tests run **in the container**; flashing, E2E and manual
tests run **on Windows in the project venv**. Never `pip install` into the
system or IDF Python. The container never touches the boards.

Once Phase 0 has delivered `tools/dev.ps1`, that script routes each command to
the right side and you should not need to think about which.

Before then, activate ESP-IDF on the host like this — `export.ps1` fails from a
plain shell because the Microsoft Store `python` alias shadows the IDF Python:

```powershell
$env:Path = "C:\Users\murilo\.espressif\tools\idf-python\3.11.2;" + $env:Path
& "C:\Users\murilo\esp\v5.5.2\esp-idf\export.ps1"
```

Shell state does not persist between tool calls — chain the export with your
command or use a wrapper script.

## 4. Binding rules

These are not style preferences. Violating one is a process failure; stop and
report rather than work around it.

1. **`docs/HARDWARE_FINDINGS.md` is normative.** Do not re-derive those numbers.
   If a new measurement contradicts it, update that document and say so
   explicitly in your report.
2. **Never weaken a pre-existing test to make your change pass.** If you break a
   test you did not write, fix your implementation or stop and ask. Loosening a
   tolerance to silence a failure is the same violation in subtler form.
3. **Worst-case tests, not just happy path** (`docs/TESTING.md` §3–4).
   Happy-path-only is incomplete, not "partially done".
4. **Fixtures use recorded real data** where the real thing was observed. Never
   hand-write plausible-looking data and present it as a recording.
5. **`domain/` includes no ESP-IDF header.** `esp_err_t` appears in no
   `domain/` or `services/` public header.
6. **Design for N anchors.** Two boards is the test fixture, not the
   architecture. Never fabricate a 3D fix below 4 anchors.
7. **Do not expand scope.** If the phase document omits something you believe is
   needed, record it in your report rather than building it.

## 5. The evidence rule

> **An acceptance criterion is ticked only when you have run the command and
> pasted its output into the report.**

- A file existing is **not** evidence.
- "Should work", "is wired up", "is implemented" are **not** evidence.
- Code you wrote but never executed is **not a deliverable**. A test harness
  that has never been run does not count as delivered, however good the code
  looks.

If you deliver a harness, **run it until it passes**. Configuration written from
memory or from documentation for a different version routinely fails on first
execution; that is exactly what running it is for.

Anything you could not run stays **explicitly unticked**, and the report says
what you tried and what happened.

## 6. Before you declare a blocker

**A blocker is a claim about the environment, and claims get verified.** Run the
checks below and paste their real output *before* writing that something is
blocked. Misdiagnosing a blocker and then building around it wastes the whole
phase.

```powershell
# Docker. NOTE: a freshly opened shell may not have docker on PATH even though
# it is installed. That is a PATH problem, not a permissions problem.
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path","User")
docker info --format '{{.ServerVersion}} / {{.OSType}}'
docker run --rm ftm-dev:latest bash -c 'idf.py --version'

# Boards — attached to the machine, not to a worktree
Get-CimInstance Win32_PnPEntity |
  Where-Object { $_.Name -match 'COM\d+' -and $_.DeviceID -match '303A' }

# A board's MAC — one command, no firmware required
.\.venv\Scripts\python.exe -m esptool --port COM3 read_mac
```

Rules that follow:

- **Never record an inability in a normative document.** Do not edit
  `docs/HARDWARE_FINDINGS.md` or `docs/CONTAINER.md` to say a value "was not
  captured". Those documents hold verified facts. If you cannot obtain a value,
  it goes in your report as an open item.
- **"Permission denied" from a missing command is a PATH problem.** Check before
  concluding otherwise.
- If a check above genuinely fails, paste the failure and **stop**. Do not
  design around an unverified blocker.

## 7. Definition of done

- [ ] Every acceptance criterion ticked **with pasted command output** (§5), or
      explicitly not-done with what you tried.
- [ ] Every harness you delivered has been **executed and passes**.
- [ ] Full suite run — **every level, not just what you touched**.
- [ ] **All work committed on your branch**, in your worktree. `git log main..HEAD`
      is non-empty; `git status` in the main worktree is clean.
- [ ] Every commit carries `Co-Authored-By: <Model Name> <noreply@anthropic.com>`.
- [ ] Report written to `docs/reports/<branch-name>.md` (`docs/WORKFLOW.md` §6).
- [ ] Branch left for human review. **Never merge to `main` yourself**, even
      when everything is green.

## 8. What the review will check

Your work is reviewed against the project's assumptions, not just whether it
builds. Self-check these before requesting review:

**Architectural drift**
- ESP-IDF headers leaking into `domain/`
- `esp_err_t` escaping into `domain/` or `services/` public headers
- Role or serialiser `#ifdef`s spreading beyond the CMake source list and the
  one accessor function
- A serialiser that includes a driver header, allocates, or performs I/O

**Assumption drift**
- Anything quietly assuming exactly two boards
- A fabricated 3D fix below 4 anchors, or a position message emitted when
  `fix_quality < 2`
- Calibration constants hardcoded rather than generated

**Test honesty** — the area scrutinised hardest
- Happy-path-only coverage presented as complete
- Hand-written fixtures presented as recorded data
- A distance assertion on a single sample, which will flake against the drift
  in `HARDWARE_FINDINGS.md` §8
- A pre-existing test weakened instead of an implementation fixed
- A synthesised `.ftmlog` presented as a recording

**Concurrency invariants** (`docs/RTOS.md`)
- Measurement blocking on transmission
- Drop-newest creeping back in — overflow discards the **oldest**
- `msg_seq` assigned at serialisation instead of enqueue, which silently
  defeats the entire loss diagnostic

**The report**
- One claiming zero deviations and all-green is usually a report that did not
  look hard enough

## 9. When blocked

Stop and ask. Specifically, do not:

- Invent a requirement the phase document does not state
- Expand scope because something "seemed needed"
- Work around a violated architectural constraint instead of reporting it
- Fabricate or predict test results you have not seen

If a decision was approved verbally but not written into a document, **get it
written into the document** — review judges against the docs, and an unwritten
deviation will be flagged as drift.
