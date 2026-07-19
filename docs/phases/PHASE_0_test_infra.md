# Phase 0 — Test Infrastructure

| | |
| --- | --- |
| **Status** | Not started |
| **Depends on** | Nothing. May run in parallel with Phase 1. |
| **Blocks** | Phase 3 (definitive firmware) |
| **Read first** | `docs/PLAN.md` §1–6, `docs/TESTING.md` (all) |

---

## Objective

Stand up the four test harnesses so that from Phase 3 onward, "write a test" is
a one-file operation rather than an infrastructure project.

**This phase writes harness + a few reference tests. It does not test features
that do not exist yet.**

## Precondition — human approval

`docs/TESTING.md` §2 contains a framework decision awaiting sign-off:
**Ceedling (Unity + CMock)** for host-side unit tests, with a **CMake + CTest
harness** as the no-Ruby fallback.

**Do not start until that is confirmed.** If the fallback is chosen, substitute
it everywhere below; the rest of the phase is unchanged.

## Context an agent needs

- Firmware is **C**, not C++. Mocks must be C mocks (this is why gmock was
  rejected — see `docs/TESTING.md` §2).
- `domain/` is designed to have **zero ESP-IDF dependencies** so it compiles and
  runs natively on the PC. That property is what this harness exploits. If a
  host test needs an ESP-IDF header, the layering has been violated — report it
  rather than working around it.
- Two boards are permanently attached: **COM3** and **COM4**.
- ESP-IDF v5.5.2. Environment setup incantation is in `docs/PLAN.md` §6 — it is
  not optional, `export.ps1` fails without it.

## Deliverables

```
test/
├── host/                          # L1: Ceedling project
│   ├── project.yml
│   ├── src/                       # symlink/include path -> components/domain
│   ├── test/
│   │   └── test_harness_smoke.c   # reference test proving the harness works
│   └── README.md
├── e2e/                           # L3: pytest + pytest-embedded
│   ├── conftest.py                # dut_responder (COM3), dut_initiator (COM4)
│   ├── test_harness_smoke.py      # both DUTs boot and are reachable
│   ├── pytest.ini                 # markers: e2e, manual, slow
│   └── README.md                  # HOW TO RUN — exact commands
└── tools/                         # L4: pytest for host Python tools
    ├── test_harness_smoke.py
    └── README.md

requirements-test.txt              # pinned pytest, pytest-embedded-*, etc.
```

Plus **one** target-side reference test app proving the L2 pattern:

```
components/drivers/peripherals/wifi/test_apps/   # created in Phase 3;
                                                  # Phase 0 only documents the pattern
```

> Phase 0 does **not** create `components/` — that is Phase 3. Phase 0 documents
> and proves the L2 invocation using a throwaway app under `test/target_smoke/`,
> then deletes it or keeps it as the template. State which you did.

## Tasks

1. **L1 host harness.** Ceedling project configured to compile
   `components/domain/**` natively. Since `components/domain` does not exist
   yet, create a minimal placeholder module (e.g. `ftm_result.h` + a trivial
   `ftm_result_to_string()`) so the harness has something real to compile, and
   write a genuine test for it including invalid-enum input. Configure CMock to
   generate mocks from headers.
2. **L2 target pattern.** Prove `idf.py -T <component> build` /
   pytest-embedded-idf can run a Unity test app on COM3. Document the exact
   command in `test/README.md`.
3. **L3 E2E harness.** `conftest.py` with **two DUT fixtures** bound to COM3 and
   COM4. Use pytest-embedded's multi-DUT support rather than hand-rolled
   pyserial. Prove it by flashing any known-good app to both and asserting both
   reach a boot marker.
   - **Known trap:** writes to these boards time out unless the firmware sets
     `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`. See `docs/HARDWARE_FINDINGS.md` §1.
     If a DUT appears unresponsive, check that first.
4. **L4 tools harness.** Plain pytest, one reference test.
5. **Markers and selection.** `pytest -m "not manual"` must run everything
   autonomous; `pytest -m manual` runs only the operator-driven test. L1/L4 must
   pass with **no hardware attached** — verify by asserting they do not import
   serial.
6. **Document how to run every level** in `test/README.md`, with exact commands
   copy-pasteable on this Windows machine.

## Required tests

The harness's own reference tests must demonstrate the worst-case discipline,
because they are the template every later phase copies:

- At least one test asserting an **error path**, not just a success path.
- At least one **CMock-based** test showing a mocked dependency returning a
  failure and the caller handling it.
- The E2E smoke test must assert on **both** DUTs, and must **fail clearly** if
  only one board is attached (not hang).

## Acceptance criteria

- [ ] `pytest -m "not manual"` runs green from a clean checkout.
- [ ] L1 suite runs with **no board attached** and completes in < 5 s.
- [ ] L3 smoke test attaches both COM3 and COM4 and asserts on both.
- [ ] Disconnecting one board produces a **clear failure message**, not a hang
      or a confusing timeout.
- [ ] `test/README.md` documents every level with exact commands.
- [ ] Ruby/Ceedling (or the fallback) install steps are documented for Windows.

## Open questions

- Should L1 coverage reporting (gcov/gcovr) be set up now or deferred? Default:
  defer, but do not structure the harness in a way that blocks it.

## Handoff

Phase 3 depends on this. Report:
- Which L1 framework was actually used (recommended or fallback).
- The exact commands for each level.
- Any deviation from `docs/TESTING.md`, with justification.
