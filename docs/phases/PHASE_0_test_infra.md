# Phase 0 — Container & Test Infrastructure

| | |
| --- | --- |
| **Status** | **Complete** — merged to `main` (`a49781e`). Report: `docs/reports/phase-0-test-infra.md` |
| **Depends on** | Nothing. May run in parallel with Phase 1. |
| **Blocks** | Phase 3 (definitive firmware) |
| **Branch** | `phase-0/test-infra` |

---

## Start here

1. **Read `docs/AGENT_BRIEF.md` first**, then the documents it lists, then this
   one in full. Also read `docs/CONTAINER.md` and `docs/TESTING.md` completely —
   this phase implements both.
2. **Create your worktree:**
   ```bash
   git worktree add ../ftm-phase-0 -b phase-0/test-infra
   cd ../ftm-phase-0
   ```
3. **Runs in parallel with Phase 1.** Do not touch `tools/bench_firmware/` or
   `tools/bench/` — that is Phase 1's territory.
4. **Done means:** acceptance criteria ticked, full suite green, report written
   to `docs/reports/phase-0-test-infra.md`, branch left for human review.

Docker Desktop, the image and the venv already work on this machine
(`docs/CONTAINER.md` §8). Your job is to turn that into reproducible tooling,
not to rediscover it.

---

## Objective

Two things:

1. **The build/test container** — everything builds and tests inside Linux,
   nothing installs into the Windows host toolchain.
2. **The test harnesses**, so that from Phase 3 onward "write a test" is a
   one-file operation rather than an infrastructure project.

**This phase writes infrastructure + reference tests. It does not test features
that do not exist yet.**

## Ground rules for this phase

- **Container scope: build + host unit tests only.** It does not touch the
  boards. No USB passthrough, no `usbipd-win`, no `--privileged`.
- **Flashing, E2E and manual tests run on Windows** in a project-local **venv**,
  against the ESP-IDF v5.5.2 already installed there.
- **Both Ceedling and the ESP-IDF Linux target**, with a strict division —
  Ceedling owns `domain/`, the Linux target owns `services/`, and **no module is
  tested in both** (`docs/TESTING.md` §2).
- **gcovr** for coverage, in the container.

Docker Desktop 4.82.0 and the image are already installed and validated
(`docs/CONTAINER.md` §8); this phase productionises that setup into
`docker/` + `tools/dev.ps1`.

## Context an agent needs

- Firmware is **C**, not C++. Mocks are C mocks via **CMock**.
- **Ruby lives in the container image only** — never installed on the PC.
- ESP-IDF Linux target verified present in v5.5.2:
  `tools/cmake/toolchain-linux.cmake`, `components/esp_system/port/soc/linux`,
  `components/unity`, `components/cmock`.
- `domain/` is designed to have **zero ESP-IDF dependencies**. If a host test
  needs a hardware header, the layering has been violated — **report it, do not
  work around it**.
- Telemetry is a **UBX-style binary protocol** (`docs/PROTOCOL.md`), implemented
  in Phase 4. Phase 0 does not implement it, but the E2E harness must not assume
  line-oriented text output.
- Two boards are permanently attached and **physically fixed 1.00 m apart**
  (`docs/HARDWARE_FINDINGS.md` §10) — the standing fixture for autonomous
  distance assertions.
- The repo already has a `.devcontainer/` using the official `espressif/idf`
  image. That is the starting point; pin it to `v5.5.2`.

## Deliverables

```
docker/
├── Dockerfile              # FROM espressif/idf:v5.5.2 + ruby/ceedling/gcovr
├── docker-compose.yml      # repo volume, ccache volume, UID mapping (NO devices)
├── entrypoint.sh           # sources export.sh (LF line endings!)
└── README.md
tools/
├── dev.ps1                 # setup|venv|build|test-host|coverage|shell|flash|e2e|manual
└── dev.sh                  # same from inside WSL/Linux
tests/
├── host_ceedling/          # L1a: Ceedling -> domain/
│   ├── project.yml
│   ├── test/test_harness_smoke.c
│   └── README.md
├── host_idf/               # L1b: ESP-IDF linux target -> services/
│   ├── CMakeLists.txt
│   ├── main/test_harness_smoke.c
│   └── README.md
├── e2e/                    # L3: pytest + pytest-embedded, multi-DUT (venv)
│   ├── conftest.py         # boards resolved BY MAC, not port
│   ├── test_harness_smoke.py
│   └── README.md           # HOW TO RUN — exact commands + duration
├── tools/                  # L4: pytest for host Python tools (venv)
│   └── test_harness_smoke.py
├── sim/                    # Lsim placeholder (populated in Phase 4)
├── manual/                 # L5 placeholder (populated in Phase 5)
├── pytest.ini              # markers: e2e, manual, slow, sim
└── README.md               # index: how to run every level, and WHERE it runs
requirements-test.txt       # pinned pytest, pytest-embedded-*, pyserial, matplotlib, numpy
docs/CONTAINER.md           # update §6 with both board MACs
```

The two host suites are **separate directories on purpose** — the division rule
in `docs/TESTING.md` §2 forbids testing a module in both.

Note `tests/` (not `test/`) — `docs/WORKFLOW.md` §4 fixes this location, and
later agents rely on it to run the whole suite.

## Task 0 — Pre-flight (do this first, paste the output)

Before writing anything, prove the environment works and **paste each result
into your report**. A previous attempt at this phase failed because it assumed
blockers instead of checking:

```powershell
# 1. Docker. If `docker` is not found, that is PATH, not permissions.
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path","User")
docker info --format '{{.ServerVersion}} / {{.OSType}}'      # expect: 29.x / linux

# 2. The image runs
docker run --rm ftm-dev:latest bash -c 'idf.py --version; ceedling version | head -3'

# 3. Both boards enumerate
Get-CimInstance Win32_PnPEntity |
  Where-Object { $_.Name -match 'COM\d+' -and $_.DeviceID -match '303A' }

# 4. Both MACs match docs/CONTAINER.md §6
.\.venv\Scripts\python.exe -m esptool --port COM3 read_mac   # 14:63:93:8d:98:74
.\.venv\Scripts\python.exe -m esptool --port COM4 read_mac   # 14:63:93:8d:96:e4
```

If any of these genuinely fails, paste the failure and **stop**. Do not design
around it.

## Tasks

1. **Install Docker Desktop** and build the image per `docs/CONTAINER.md`. Must
   satisfy: repo mounted not copied; container build dir `build_container/`
   separate from any host `build/`; UID mapped so files are not root-owned;
   ccache volume persisted; LF line endings on all shell scripts
   (`.gitattributes` enforces this — verify it took effect). **No device
   mapping, no `--privileged`.**
2. **L1a Ceedling harness** (container) targeting `components/domain/**`.
   `components/domain` does not exist yet, so create a minimal real module
   (`ftm_result.h` + `ftm_result_to_string()`) and write a genuine test for it
   **including an out-of-range enum value**. Prove CMock generates a mock from a
   header.
   - **Run `ceedling test:all` until it passes and paste the output.** Read
     `docs/CONTAINER.md` §7 "Ceedling 1.1.0 specifics" first — four known
     config traps live there, all of which only appear on execution.
3. **L1b ESP-IDF linux-target harness** (container) targeting `components/
   services/**`. Same approach: a minimal real module and a real test.
   - **Run it.** Both `idf.py --preview set-target linux build` **and** the
     resulting binary must be executed, with output pasted. The test must call
     `exit(failures)` after `UNITY_END()`, or it hangs instead of failing
     (`docs/CONTAINER.md` §7).
4. **gcovr coverage** wired over L1a, output to `build_container/coverage/`
   as HTML + XML. Report the actual numbers; do **not** enforce the proposed
   thresholds as a hard gate yet (`docs/TESTING.md` §2).
5. **Python venv** (`.venv/`, git-ignored) with `requirements-test.txt`.
   `dev.ps1 venv` must create it. Nothing may install into the system or IDF
   Python.
6. **L2 target pattern.** Prove a Unity `test_apps` build runs on a real board.
   Document the exact command. Use a throwaway app under `tests/target_smoke/`;
   state whether you kept it as a template or removed it.
7. **L3 E2E harness** (host venv). `conftest.py` with **two DUT fixtures**,
   using pytest-embedded multi-DUT rather than hand-rolled pyserial. Resolve
   boards **by MAC address** (`docs/CONTAINER.md` §6) — ports re-enumerate.
   Prove it by flashing a known-good app to both and asserting both reach a boot
   marker.
   - **Known trap:** serial writes time out unless firmware sets
     `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` (`HARDWARE_FINDINGS.md` §1). Boot
     logs still appear, which makes this look like a different problem.
   - **Known trap:** opening a port resets the board. A responder's AP state
     will not survive a per-step port open — hold both ports for the whole test.
8. **L4 tools harness** (host venv). Plain pytest, one reference test.
9. **Markers and selection.** `pytest -m "not manual"` runs everything
   autonomous; `pytest -m manual` runs only operator-driven tests. L1a/L1b must
   pass with **no hardware attached** — assert they never import `serial`.
10. **`dev.ps1` routing.** Each subcommand goes to the right side (container vs.
    host venv) without the caller needing to know which.
11. **Verify both board MACs** against `docs/CONTAINER.md` §6 (already recorded:
    A = `14:63:93:8d:98:74`, B = `14:63:93:8d:96:e4`). Correct the document only
    if a measurement disagrees.
12. **Document every level** in `tests/README.md`: exact copy-pasteable command,
    **where it runs** (container or host venv), and expected duration so a slow
    suite is not mistaken for a hang.

## Required tests

The reference tests are the template every later phase copies, so they must
demonstrate worst-case discipline. Minimum set:

**L1a (Ceedling, `domain/`)**
- A known-good value.
- An **out-of-range enum** value.
- A **NULL argument** rejected.
- A **buffer-too-small** case, asserting a canary byte past the limit is
  untouched.
- A **CMock** test where the mocked dependency **succeeds**, and another where
  it **fails** and the caller handles it.

**L1b (ESP-IDF linux target, `services/`)**
- A nominal case.
- The **clamp signature** from `HARDWARE_FINDINGS.md` §6: `valid=2, total=30`
  must be judged unusable even though the session reported success.
- The 0.8 quality boundary (`valid=24, total=30`).
- **Impossible counts** (`valid > total`) rejected.

**L3 (E2E)**
- Asserts on **both** DUTs.
- **Fails clearly** if only one board is attached — never hangs.

Every one of these must be **executed**, not merely written
(`docs/AGENT_BRIEF.md` §5).

## Acceptance criteria

**Every box below requires pasted command output in the report**
(`docs/AGENT_BRIEF.md` §5). A file existing is not evidence.

- [ ] Task 0 pre-flight output pasted: Docker version, container `idf.py`,
      both boards enumerated, both MACs.
- [ ] Container builds firmware from a clean checkout with **no host ESP-IDF**
      involved.
- [ ] `.\tools\dev.ps1 test-host` runs **both L1a and L1b** green in the
      container, with no board attached. Output pasted showing both suites and
      their pass counts.
- [ ] `.\tools\dev.ps1 coverage` produces a gcovr report with **non-zero
      line counts** (a 0 % report is a wiring failure, not a pass).
- [ ] `.\tools\dev.ps1 venv` creates `.venv/`; nothing installed into system or
      IDF Python.
- [ ] `.\tools\dev.ps1 flash <role>` flashes the board matching that role's
      **MAC** and fails loudly if it is absent. Demonstrate **both** the success
      path and the missing-board path.
- [ ] `.\tools\dev.ps1 e2e` runs the L3 smoke test against **both** boards from
      the venv, asserting on both. Fixtures that unconditionally skip do not
      satisfy this.
- [ ] Disconnecting a board gives a **clear message**, not a hang — demonstrated.
- [ ] Generated files on the host are owned by the user, not root.
- [ ] Container has **no** device mapping and does not run privileged.
- [ ] Every directory in the Deliverables tree exists, including
      `tests/sim/`, `tests/manual/` and `tests/target_smoke/`. `dev.ps1` must
      not reference a path that does not exist.
- [ ] `tests/README.md` documents every level: command, where it runs, duration.
- [ ] Board MACs in `docs/CONTAINER.md` §6 verified against hardware.
- [ ] **All work committed on `phase-0/test-infra`, inside the phase worktree.**
      `git log main..HEAD` non-empty; `git status` in the main checkout clean;
      every commit carries the `Co-Authored-By` trailer.

## Decisions in force

- **Coverage is reported, not gated.** Emit the gcovr numbers; do not fail the
  build on the `docs/TESTING.md` §2 thresholds. Those become a gate only once
  real modules exist to measure — a threshold set before there is anything to
  measure only teaches people to game it.
- **No Xvfb in the container.** The Phase 2 tkinter UI runs on Windows for the
  operator; its logic lives in a tkinter-free `model.py` and is tested
  headlessly. Enforce that split rather than adding a display server.

## Handoff

Phase 3 depends on this. Report:
- The exact command for each test level, where it runs, and its duration.
- Actual coverage numbers.
- Both board MACs.
- Any deviation from `docs/TESTING.md` or `docs/CONTAINER.md`, with
  justification.
- Full test output, per `docs/WORKFLOW.md` §2.
