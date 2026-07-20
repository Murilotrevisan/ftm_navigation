# FTM Indoor Positioning — Master Plan

> **Agents: start at `docs/AGENT_BRIEF.md`**, then your phase document under
> `docs/phases/`. Each phase document opens with a **Start here** block giving
> its branch, worktree command, dependencies and definition of done — it is a
> complete work order.
>
> This document is the index and the source of the project-wide constraints
> (§5). `docs/HARDWARE_FINDINGS.md` is normative measured fact.

---

## 1. Goal

Build a **3D indoor positioning system** from ESP32-C3 boards using Wi-Fi FTM
(Fine Timing Measurement).

- **One initiator** (mobile node) measures its distance to **several anchors**
  (stationary FTM responders).
- Distances plus known anchor positions give a 3D fix by trilateration.
- **Target accuracy is not demanding** — the FTM hardware quantises to 15 cm and
  that is explicitly acceptable for this project. This is a feasibility bench,
  not a metrology instrument.
- **Currently available hardware: 2× ESP32-C3.** Everything must be *designed*
  for N anchors and *validated* with 2. Never hardcode a two-board assumption.

## 2. Current state

| Item | Status |
| --- | --- |
| ESP-IDF v5.5.2 at `C:\Users\murilo\esp\v5.5.2` | Working |
| Board A — COM3, ESP32-C3 | Working, used as responder |
| Board B — COM4, ESP32-C3 rev v0.4, MAC `14:63:93:8d:96:e4` | Working, used as initiator |
| Espressif FTM console example | Built, flashed, end-to-end FTM verified |
| Measured baseline at ~1.2 m separation | mean 1.22 m, 28–30/30 valid readings |
| **Bench fixture: boards fixed 1.00 m apart** | Standing setup — tests may assert 1 m ground truth |
| Git repository | Initialised, branch `main` |
| Docker Desktop 4.82.0 + `ftm-dev` image | Installed; firmware build, Ceedling, IDF linux target all verified |
| Python venv + test libs | Installed and verified |

All hardware facts are in **`docs/HARDWARE_FINDINGS.md`**. That document is
normative — do not re-derive these numbers, and do not contradict them without
new measurements.

## 3. Repository layout (target)

```
ftm_measurement/
├── docs/
│   ├── PLAN.md                   <- this file
│   ├── AGENT_BRIEF.md            <- agent onboarding; read before any phase
│   ├── HARDWARE_FINDINGS.md      <- verified measurements, normative
│   ├── ARCHITECTURE.md           <- layering, swappable modules, contracts
│   ├── RTOS.md                   <- tasks, queue, overflow policy
│   ├── TESTING.md                <- test framework + worst-case catalogue
│   ├── CONTAINER.md              <- container (build + host unit tests only)
│   ├── PROTOCOL.md               <- ftmbin wire format (one serialiser)
│   ├── WORKFLOW.md               <- git rules, merge gate, reports
│   └── phases/
│       ├── PHASE_0_test_infra.md
│       ├── PHASE_1_bench_firmware.md
│       ├── PHASE_2_calibrator.md
│       ├── PHASE_3_definitive_firmware.md
│       ├── PHASE_4_protocol.md
│       ├── PHASE_5_positioning.md
│       └── PHASE_6_e2e_and_manual.md
├── tools/
│   ├── bench_firmware/           <- Phase 1: board validation firmware
│   ├── bench/                    <- Phase 1: host validation scripts
│   └── calibrator/               <- Phase 2: firmware + tkinter UI
├── components/                   <- Phase 3: the definitive layered firmware
│   ├── domain/
│   ├── services/
│   └── drivers/
├── docker/                       <- Phase 0: build/test container
└── tests/                        <- all committed tests (WORKFLOW.md §4)
```

There is deliberately **no ESP-IDF project at the repository root**. Phase 1
moved the bench example into `tools/bench_firmware/`; the definitive firmware
(Phase 3) lives in `components/` with its own project. A root `main/` would be
ambiguous about which firmware it belongs to.

## 4. Phase overview

Phases are ordered by dependency. Each is independently assignable.

| Phase | Deliverable | Depends on | Doc |
| --- | --- | --- | --- |
| **0** ✅ | Container + test infrastructure — **merged** | — | [PHASE_0](phases/PHASE_0_test_infra.md) |
| **1** ✅ | Bench validation firmware in `tools/` — **merged** | — | [PHASE_1](phases/PHASE_1_bench_firmware.md) |
| **2** | Calibration firmware + tkinter UI → CSV | 1 | [PHASE_2](phases/PHASE_2_calibrator.md) |
| **3** | Definitive layered firmware | 0, 2 | [PHASE_3](phases/PHASE_3_definitive_firmware.md) |
| **4** | Binary protocol + `.ftmlog` logging + replay | 3 | [PHASE_4](phases/PHASE_4_protocol.md) |
| **5** | Positioning — host-first from logs, then target | 3, 4 | [PHASE_5](phases/PHASE_5_positioning.md) |
| **6** | E2E suite + human-in-loop movement test | 3, 4, 5 | [PHASE_6](phases/PHASE_6_e2e_and_manual.md) |

Phases 0 and 1 have no dependencies and may run in parallel.

**Phase 4 exists so Phase 5 can be done offline.** The protocol, `.ftmlog`
capture and replay tooling let the 3D algorithm be developed and proven on the
host against recorded real measurements — with their real noise and drift —
before any of it is compiled for the target. Phase 5 is then split: **5a host,
5b target, one shared source file**.

The container and all toolchains are installed and validated
(`docs/CONTAINER.md` §8).

## 5. Non-negotiable constraints

These apply to every phase. An agent violating one should stop and flag it.

1. **Every feature has unit tests covering worst-case behaviour, not just the
   happy path.** See the worst-case catalogue in `docs/TESTING.md` §4. A PR with
   only happy-path tests is incomplete.
2. **Every feature is exercised end-to-end on real hardware.** Both boards are
   permanently connected on COM3 and COM4. E2E tests run autonomously.
3. **The layering in `docs/ARCHITECTURE.md` is mandatory**, including layers that
   are currently empty (`drivers/devices/`). Empty layers exist for
   standardisation and get a `README.md` explaining why they are empty.
4. **Swappable modules follow one pattern** — interface vtable, Kconfig-selected
   implementation, shared contract suite (`docs/ARCHITECTURE.md` §2). This
   covers role selection and serialisation. No `#ifdef` scattered through
   business logic.
5. **Serialisation is a swappable module**, consuming domain snapshots and
   producing bytes. It must not include a driver or ESP-IDF header, must not
   allocate, and must not perform I/O. Every implementation passes the shared
   contract suite (`docs/TESTING.md` §4.8).
6. **The measurement task never blocks on transmission** (`docs/RTOS.md`). On
   queue overflow the **oldest** entry is discarded so the freshest reading
   always survives — this is a navigation system, and stale data is worse than
   no data. Loss is made observable by a `msg_seq` gap plus a `dropped_total`
   counter, both **diagnostic only**: navigation uses current data and never
   waits for or reconstructs missing messages.
7. **Design for N anchors.** Two boards is the current test fixture, not the
   architecture. With fewer than 4 usable anchors the system reports
   **`RANGE_ONLY`** — per-station distances — and never fabricates a 3D fix.
8. **Fix status travels with the data.** Every cycle sends `NAV-STATUS` with
   `fix_quality` and `num_anchors`. **Absence is information: no `NAV-POSITION`
   message means no position.** Never emit a position message with placeholder
   or zeroed coordinates — zero is a valid coordinate (`docs/PROTOCOL.md`).
9. **Never hardcode calibration constants in logic.** They come from the
   generated calibration table (Phase 2 output).
10. **Builds and host unit tests run in the container**; flashing, E2E and manual
    tests run on Windows **inside the project venv** (`docs/CONTAINER.md`).
    Never `pip install` into the system or IDF Python. The container never
    touches the boards.
11. **Branch per feature; `main` is never committed to directly.** Merges are
    human-approved after all tests pass and the results have been shown.
12. **Never weaken a pre-existing test to make your change pass.** If you break
    a test you did not write, fix your implementation or stop and ask. This is
    the regression rule in `docs/WORKFLOW.md` §3 and it is absolute.
13. **Every branch ends with a work report** at `docs/reports/<branch>.md`
    stating deviations and scope changes, and every commit carries the
    `Co-Authored-By` model trailer (`docs/WORKFLOW.md` §5–6).

## 6. Environment setup (every agent needs this)

Once Phase 0 is done, `tools/dev.ps1` routes every command to the right place —
container or host — and an agent should not need to think about which:

```powershell
.\tools\dev.ps1 build            # container
.\tools\dev.ps1 test-host        # container: Ceedling + IDF linux target
.\tools\dev.ps1 coverage         # container: gcovr
.\tools\dev.ps1 flash responder  # Windows host
.\tools\dev.ps1 e2e              # Windows host, venv
```

### Host ESP-IDF

The Windows host has ESP-IDF v5.5.2 at `C:\Users\murilo\esp\v5.5.2`, used for
flashing and E2E.

`export.ps1` fails from a plain PowerShell session because the Microsoft Store
`python` alias shadows the IDF Python. Always prepend the IDF Python first:

```powershell
$env:Path = "C:\Users\murilo\.espressif\tools\idf-python\3.11.2;" + $env:Path
& "C:\Users\murilo\esp\v5.5.2\esp-idf\export.ps1"
```

Shell state does not persist between tool calls — chain the export with the
command, or use a wrapper script.

**Console must be on USB-Serial-JTAG.** These boards expose only the built-in
USB-Serial-JTAG (VID `303A` / PID `1001`), not a UART bridge. Any firmware in
this repo must set:

```
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y
```

Without it the REPL is unreachable and the failure is misleading: boot logs still
appear on the COM port, but every write times out.

## 7. How agents should work these documents

- **Read your phase doc fully before starting.** It lists preconditions,
  deliverables with exact paths, required tests, and acceptance criteria.
- **Do not expand scope.** If a phase doc omits something you think is needed,
  record it in your work report (`docs/WORKFLOW.md` §6) rather than building it.
- **Record measurements, don't assume them.** If you take a new hardware
  reading that contradicts `docs/HARDWARE_FINDINGS.md`, update that document and
  say so explicitly in your report.
- **Update the phase doc's status table** when you finish.
- **Report honestly.** If a test fails or a step was skipped, say so with the
  output. Do not describe unverified work as verified.
