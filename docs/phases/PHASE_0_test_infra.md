# Phase 0 — Container & Test Infrastructure

| | |
| --- | --- |
| **Status** | Not started |
| **Depends on** | Nothing. May run in parallel with Phase 1. |
| **Blocks** | Phase 3 (definitive firmware) |
| **Read first** | `docs/PLAN.md` (all), `docs/CONTAINER.md` (all), `docs/TESTING.md` (all), `docs/WORKFLOW.md` (all) |

---

## Objective

Two things:

1. **The build/test container** — everything builds and tests inside Linux,
   nothing installs into the Windows host toolchain.
2. **The test harnesses**, so that from Phase 3 onward "write a test" is a
   one-file operation rather than an infrastructure project.

**This phase writes infrastructure + reference tests. It does not test features
that do not exist yet.**

## Precondition — human decision

`docs/CONTAINER.md` §2 needs an answer before the container can be built:

- **Which container runtime?** Docker Desktop / Podman Desktop / Docker Engine
  inside the existing WSL2 Ubuntu. `docker` is **not currently installed**;
  WSL2 + Ubuntu **is**.
- **Option A or B?** A = container builds and unit-tests, Windows host flashes
  (no `usbipd-win`, but E2E lives outside the container). B = container does
  everything including flash and E2E (needs `usbipd-win` on the host).
  **Recommendation: B.**

**Do not start the container work until this is answered.** The harness work
(tasks 2–6) can begin regardless.

> The framework question is **settled** — ESP-IDF's own Linux target + Unity +
> CMock. No Ruby, no Ceedling. See `docs/TESTING.md` §2.

## Context an agent needs

- Firmware is **C**, not C++. Mocks are C mocks via **CMock**, which is bundled
  in ESP-IDF at `components/cmock` (verified present in v5.5.2).
- L1 host tests use **`idf.py --preview set-target linux`** — ESP-IDF's own
  host-test mechanism. Verified present: `tools/cmake/toolchain-linux.cmake`
  and `components/esp_system/port/soc/linux`.
- `domain/` is designed to have **zero ESP-IDF dependencies** so it builds for
  the linux target. If a host test needs a hardware header, the layering has
  been violated — **report it, do not work around it**.
- Two boards are permanently attached and **physically fixed 1.00 m apart**
  (`docs/HARDWARE_FINDINGS.md` §10) — the standing fixture for autonomous
  distance assertions.
- The repo already has a `.devcontainer/` using the official `espressif/idf`
  image. That is the starting point; pin it to `v5.5.2`.

## Deliverables

```
docker/
├── Dockerfile              # FROM espressif/idf:v5.5.2 + test toolchain
├── docker-compose.yml      # volumes, device passthrough, UID mapping
├── entrypoint.sh           # sources export.sh (LF line endings!)
└── README.md
tools/
├── dev.ps1                 # dev.ps1 setup|build|test|test-host|flash|e2e|manual|shell
├── dev.sh                  # same from inside WSL/Linux
└── attach_boards.ps1       # usbipd bind+attach (Option B only)
tests/
├── host/                   # L1: ESP-IDF linux target + Unity + CMock
│   ├── CMakeLists.txt
│   ├── main/test_harness_smoke.c
│   └── README.md
├── e2e/                    # L3: pytest + pytest-embedded, multi-DUT
│   ├── conftest.py         # boards resolved BY MAC, not port
│   ├── test_harness_smoke.py
│   └── README.md           # HOW TO RUN — exact commands + duration
├── tools/                  # L4: pytest for host Python tools
│   └── test_harness_smoke.py
├── sim/                    # Lsim placeholder (populated in Phase 4)
├── manual/                 # L5 placeholder (populated in Phase 5)
├── pytest.ini              # markers: e2e, manual, slow, sim
└── README.md               # index: how to run every level
requirements-test.txt       # pinned pytest, pytest-embedded-*, matplotlib, numpy
docs/CONTAINER.md           # update §2 to record the decision actually taken
```

Note `tests/` (not `test/`) — `docs/WORKFLOW.md` §4 fixes this location, and
later agents rely on it to run the whole suite.

## Tasks

1. **Container.** Build it per `docs/CONTAINER.md`. Must satisfy: repo mounted
   not copied; container build dir separate from any host `build/`; UID mapped
   so files are not root-owned; ccache volume persisted; LF line endings on all
   shell scripts (`.gitattributes` enforces this — verify it took effect).
2. **L1 host harness.** An ESP-IDF linux-target test app compiling
   `components/domain/**`. `components/domain` does not exist yet, so create a
   minimal real module (`ftm_result.h` + `ftm_result_to_string()`) and write a
   genuine test for it **including an out-of-range enum value**. Wire CMock and
   prove mock generation works on at least one header.
3. **L2 target pattern.** Prove a Unity `test_apps` build runs on a real board.
   Document the exact command. Use a throwaway app under `tests/target_smoke/`;
   state whether you kept it as the template or removed it.
4. **L3 E2E harness.** `conftest.py` with **two DUT fixtures**, using
   pytest-embedded multi-DUT rather than hand-rolled pyserial. Resolve boards
   **by MAC address** (`docs/CONTAINER.md` §5) — port numbers re-enumerate.
   Prove it by flashing a known-good app to both and asserting both reach a boot
   marker.
   - **Known trap:** serial writes time out unless firmware sets
     `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` (`HARDWARE_FINDINGS.md` §1). Boot
     logs still appear, which makes this look like something else.
   - **Known trap:** opening a port resets the board. A responder's AP state
     will not survive a per-step port open — hold both ports for the whole test.
5. **L4 tools harness.** Plain pytest, one reference test.
6. **Markers and selection.** `pytest -m "not manual"` runs everything
   autonomous; `pytest -m manual` runs only operator-driven tests. L1/L4 must
   pass with **no hardware attached** — assert they never import `serial`.
7. **Record the board MAC table** in `docs/CONTAINER.md` §5. Board B is
   `14:63:93:8d:96:e4`; Board A's MAC is not yet recorded — capture it.
8. **Document every level** in `tests/README.md` with exact copy-pasteable
   commands, and state the expected duration of each so a slow suite is not
   mistaken for a hang.

## Required tests

The harness's own reference tests must demonstrate the worst-case discipline,
because they are the template every later phase copies:

- At least one test asserting an **error path**, not just a success path.
- At least one **CMock-based** test showing a mocked dependency returning a
  failure and the caller handling it.
- The E2E smoke test must assert on **both** DUTs, and must **fail clearly** if
  only one board is attached (not hang).

## Acceptance criteria

- [ ] Container builds from a clean checkout with **no host ESP-IDF** involved.
- [ ] `.\tools\dev.ps1 test` runs the full autonomous suite green.
- [ ] `.\tools\dev.ps1 build` produces firmware; `flash <role>` flashes the
      board matching that role's **MAC**, and fails loudly if it is absent.
- [ ] L1 suite runs with **no board attached**, in the container, in seconds.
- [ ] L3 smoke test attaches **both** boards and asserts on both.
- [ ] Disconnecting one board gives a **clear message**, not a hang. If Option B,
      the message names the exact `usbipd attach` command to run.
- [ ] Generated files on the host are owned by the user, not root.
- [ ] `tests/README.md` documents every level with exact commands and durations.
- [ ] `docs/CONTAINER.md` §2 updated with the decision actually taken, and §5
      updated with both board MACs.
- [ ] Work done on a `phase-0/...` branch; `main` untouched
      (`docs/WORKFLOW.md` §1).

## Open questions

- L1 coverage reporting (gcov/gcovr) now or deferred? Default: defer, but do not
  structure the harness in a way that blocks it.
- Should the container also run a headless X/Xvfb so the Phase 2 tkinter UI can
  be smoke-tested inside it? The UI itself is operator-facing and will run on
  Windows, but its logic is testable headlessly if `model.py` stays tkinter-free
  as Phase 2 requires. Recommend: no Xvfb; enforce the split instead.

## Handoff

Phase 3 depends on this. Report:
- Container runtime and Option A/B actually used.
- The exact command for each test level, and its duration.
- Both board MACs.
- Any deviation from `docs/TESTING.md` or `docs/CONTAINER.md`, with
  justification.
- Full test output, per `docs/WORKFLOW.md` §2.
