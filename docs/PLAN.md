# FTM Indoor Positioning — Master Plan

> **Read this first.** This document is the index. Each phase has its own
> self-contained document under `docs/phases/`. An agent assigned a phase should
> read: this file (sections 1–7), `docs/HARDWARE_FINDINGS.md`,
> `docs/WORKFLOW.md`, `docs/CONTAINER.md`, and its own phase document. Only read
> other phase documents if the handoff section says to.
>
> **Before writing any code, read `docs/WORKFLOW.md`.** It contains the
> branching rules, the merge gate, and the regression rule — all binding.

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
| Git repository | Initialised, branch `main`, initial commit present |
| Build/test container | **Not built** — Phase 0 deliverable, one open decision |

All hardware facts are in **`docs/HARDWARE_FINDINGS.md`**. That document is
normative — do not re-derive these numbers, and do not contradict them without
new measurements.

## 3. Repository layout (target)

```
ftm_measurement/
├── docs/
│   ├── PLAN.md                   <- this file
│   ├── HARDWARE_FINDINGS.md      <- verified measurements, normative
│   ├── ARCHITECTURE.md           <- layering, strategy pattern, contracts
│   ├── TESTING.md                <- test framework + worst-case catalogue
│   ├── CONTAINER.md              <- build/test/flash container (ONE OPEN DECISION)
│   ├── WORKFLOW.md               <- git rules, merge gate, regression rule
│   └── phases/
│       ├── PHASE_0_test_infra.md
│       ├── PHASE_1_bench_firmware.md
│       ├── PHASE_2_calibrator.md
│       ├── PHASE_3_definitive_firmware.md
│       ├── PHASE_4_multi_station.md
│       └── PHASE_5_e2e_and_manual.md
├── tools/
│   ├── bench_firmware/           <- Phase 1: board validation firmware
│   ├── bench/                    <- Phase 1: host validation scripts
│   └── calibrator/               <- Phase 2: firmware + tkinter UI
├── components/                   <- Phase 3: the definitive layered firmware
│   ├── domain/
│   ├── services/
│   └── drivers/
├── main/
└── test/
```

## 4. Phase overview

Phases are ordered by dependency. Each is independently assignable.

| Phase | Deliverable | Depends on | Doc |
| --- | --- | --- | --- |
| **0** | Test infrastructure + framework decision | — | [PHASE_0](phases/PHASE_0_test_infra.md) |
| **1** | Bench validation firmware in `tools/` | — | [PHASE_1](phases/PHASE_1_bench_firmware.md) |
| **2** | Calibration firmware + tkinter UI → CSV | 1 | [PHASE_2](phases/PHASE_2_calibrator.md) |
| **3** | Definitive layered firmware | 0, 2 | [PHASE_3](phases/PHASE_3_definitive_firmware.md) |
| **4** | Multi-station scaling + trilateration | 3 | [PHASE_4](phases/PHASE_4_multi_station.md) |
| **5** | E2E suite + human-in-loop movement test | 3, 4 | [PHASE_5](phases/PHASE_5_e2e_and_manual.md) |

Phases 0 and 1 have no dependencies and may run in parallel.

**Phase 0 contains a decision that requires human review before Phase 3 starts.**
Do not begin Phase 3 until the test framework choice in `docs/TESTING.md` is
approved.

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
4. **Role selection (initiator vs responder) uses the Strategy pattern, selected
   by Kconfig.** No `#ifdef` scattered through business logic.
5. **Design for N anchors.** Two boards is the current test fixture, not the
   architecture. With fewer than 4 usable anchors the system reports
   **`RANGE_ONLY`** — per-station distances — and never fabricates a 3D fix.
   See `docs/ARCHITECTURE.md` §4.
6. **Never hardcode calibration constants in logic.** They come from the
   generated calibration table (Phase 2 output).
7. **All builds and tests run in the container** (`docs/CONTAINER.md`). Nothing
   is installed into the Windows host toolchain.
8. **Branch per feature; `main` is never committed to directly.** Merges are
   human-approved after all tests pass and the results have been shown. See
   `docs/WORKFLOW.md`.
9. **Never weaken a pre-existing test to make your change pass.** If you break
   a test you did not write, fix your implementation or stop and ask. This is
   the regression rule in `docs/WORKFLOW.md` §3 and it is absolute.

## 6. Environment setup (every agent needs this)

**Use the container** (`docs/CONTAINER.md`). All builds and tests run there.
Once Phase 0 is done this is the whole story:

```powershell
.\tools\dev.ps1 test        # all autonomous tests
.\tools\dev.ps1 build
.\tools\dev.ps1 flash responder
```

### Host ESP-IDF (legacy path, pre-container only)

The Windows host also has ESP-IDF v5.5.2 at `C:\Users\murilo\esp\v5.5.2`. It was
used for the initial evaluation and remains usable, but **new work should not
depend on it**.

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
  note it in the phase's "Open questions" section rather than building it.
- **Record measurements, don't assume them.** If you take a new hardware
  reading that contradicts `docs/HARDWARE_FINDINGS.md`, update that document and
  say so explicitly in your report.
- **Update the phase doc's status table** when you finish.
- **Report honestly.** If a test fails or a step was skipped, say so with the
  output. Do not describe unverified work as verified.
