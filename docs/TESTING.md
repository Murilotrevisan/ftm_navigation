# Testing Strategy — Proposal for Review

> **STATUS: AWAITING APPROVAL.** Section 2 contains a framework decision that
> needs a human sign-off before Phase 3 begins. Everything else follows from it.

---

## 1. Test levels

| Level | Scope | Framework | Runs on | Speed |
| --- | --- | --- | --- | --- |
| **L1 Unit — host** | `domain/types`, `domain/core`, `services/*` | Unity + CMock (via Ceedling) | PC, no hardware | < 1 s |
| **L2 Unit — target** | `drivers/peripherals/wifi` | Unity (ESP-IDF `test_apps`) | ESP32-C3 | ~30 s |
| **L3 E2E — two boards** | Full firmware, both roles | pytest + pytest-embedded | COM3 + COM4 | minutes |
| **L4 Host tools** | calibrator UI, codegen scripts | pytest | PC | seconds |
| **L5 Manual integration** | Physical movement → chart | pytest, human-in-loop | COM3 + COM4 + operator | ~10 min |

The layering in `docs/ARCHITECTURE.md` exists to make L1 possible: `domain/` has
zero ESP-IDF dependencies, so the bulk of the logic is testable in under a
second with no board attached.

## 2. Framework decision (REVIEW REQUIRED)

### Recommended

**L1 — Ceedling (Unity + CMock).**
- CMock **generates C mocks directly from headers** — point it at
  `wifi_ftm.h` and it produces `mock_wifi_ftm.c` with expectation/stub APIs. No
  hand-written fakes to drift out of sync.
- Unity is already ESP-IDF's test framework, so assertions look the same at L1
  and L2 — one idiom for the whole project.
- Sub-second feedback on the pure logic, which is where the interesting
  worst-case behaviour lives (clamp, overflow, degenerate geometry).
- **Cost: requires Ruby on Windows** (`winget install RubyInstaller.Ruby`).
  One-time setup.

**L2 — Unity via ESP-IDF `test_apps`.** The standard ESP-IDF 5.x pattern
(`components/<name>/test_apps/`), driven by pytest-embedded. Anything touching
`esp_wifi` must run on silicon; there is no meaningful way to fake the FTM
hardware timing path.

**L3/L5 — pytest + `pytest-embedded-serial-esp` + `pytest-embedded-idf`.**
Espressif's own E2E harness. Handles build, flash, serial attach, and log
expectation for **multiple DUTs in one test** — which is exactly the two-board
topology. Multi-DUT is a first-class feature (`--count 2`), so the two boards
become `dut[0]` and `dut[1]` rather than hand-rolled serial plumbing.

**L4 — plain pytest.** The calibrator is Python; nothing exotic needed.

### Rejected, with reasons

| Option | Why not |
| --- | --- |
| **gmock / gtest** | C++ frameworks. The firmware is C. Wrapping C modules in C++ fixtures adds friction, and CMock generates C mocks from the real headers with less ceremony. Would only make sense if the firmware were C++. |
| **Hand-written fakes instead of CMock** | Drift. A fake that isn't regenerated from the header silently diverges when the interface changes, and the test keeps passing. |
| **ESP-IDF `linux` target for L1** | Attractive (no Ruby), but on Windows it needs WSL, adding a heavier dependency than Ruby. Worth revisiting if the team moves to Linux CI. |
| **Everything on-target** | Too slow to run per-edit; kills the feedback loop that makes worst-case testing practical. |

### The one real risk

Ceedling's Ruby dependency on Windows. **Fallback if rejected:** a CMake +
Unity + CMock host harness driven by CTest — no Ruby, but the mock generation
step must be wired manually and there is more boilerplate per test target.

> **Reviewer: please confirm or redirect the L1 choice (Ceedling vs. CMake/CTest
> harness). Everything else is low-controversy.**

## 3. Coverage requirement

> Every feature has unit tests covering worst-case behaviour, not just the happy
> path. Happy-path-only is **incomplete**, not "partially done".

Concretely, for each public function:

1. Nominal case.
2. Every documented failure mode.
3. Every boundary of every numeric input.
4. Invalid/NULL arguments.
5. The failure modes catalogued in §4 that apply to it.

## 4. Worst-case catalogue

Derived from `docs/HARDWARE_FINDINGS.md`. These are **real observed hazards**,
not hypotheticals. Agents must cover the ones relevant to their module.

### 4.1 Distance / calibration math (`domain/core/ftm_distance`)

| Case | Why it matters | Reference |
| --- | --- | --- |
| Reported distance clamped at 0 | `dist_est` is unsigned and saturates; a real 0 is indistinguishable from a clamp | §4 |
| Offset over-correction → negative distance | Must produce a signed negative or an explicit error, **never** a `uint32` wrap to ~4e9 | §4 |
| Inverted offset sign | `reported ≈ true − offset`. A sign error is silent and plausible-looking | §5 |
| 15 cm quantisation | Any test asserting equality on `dist_est` must respect the 0.15 m grid | §3 |
| `rtt_raw` = 0 with valid readings | Legitimate near-field case, must not divide by zero or assert | §4 |
| `UINT32_MAX` sentinel in per-frame `rtt` | The example checks for this; means "invalid entry" | — |

### 4.2 Quality / filtering (`domain/core/ftm_filter`)

| Case | Why it matters | Reference |
| --- | --- | --- |
| valid/total = 2/30 but status == success | The clamp signature. Must be rejected as invalid | §6 |
| Slow drift (1.23 m → 0.10 m, fixed setup) | Filter must not silently track drift as if it were motion | §8 |
| All samples in window rejected | Must return "no estimate", not a stale or zero value | §8 |
| Single-sample window | Median/EMA boundary | — |
| Empty window / window not yet full | Startup transient | — |
| Outlier spike (0.75 → 1.65 m between adjacent samples) | Observed real spread; must not be treated as a fault | §7 |

### 4.3 Trilateration (`domain/core/ftm_trilateration`)

| Case | Required behaviour |
| --- | --- |
| Fewer than 4 anchors | Explicit `FTM_ERR_INSUFFICIENT_ANCHORS`, not a garbage fix |
| Coplanar anchors | Detect degeneracy; 3D solve is ambiguous |
| Collinear anchors | Detect degeneracy |
| Duplicate anchor positions | Reject, do not produce a singular matrix |
| No intersection (inconsistent ranges) | Return best-fit **with a residual**, so the caller can judge it |
| Anchor with missing/stale measurement | Solve with the remainder or fail explicitly — never use a stale range silently |
| Numerical: very large / very small ranges | No overflow, no NaN escaping to callers |

### 4.4 Driver layer (`drivers/peripherals/wifi`)

| Case | Required behaviour |
| --- | --- |
| FTM session timeout (no report event) | Session ended cleanly, report drained, error returned |
| `FTM_STATUS_USER_TERM` | Distinguished from failure |
| Report requested but allocation fails | No crash, no leak |
| **Report drained on the failure path** | The example leaks here — see §9. Must be covered by an explicit test |
| Session started while one is in progress | Rejected, not queued silently |
| Peer BSSID not found / wrong channel | Explicit error |
| `esp_wifi_ftm_get_report` with `NULL, 0` | Valid — frees internal report without copying |

### 4.5 Scheduler / multi-anchor (`services/middleware/ftm_scheduler`)

| Case | Required behaviour |
| --- | --- |
| Zero anchors configured | Explicit error at init |
| One anchor unreachable in a cycle | Cycle completes with a partial result, marked partial |
| All anchors unreachable | No fix produced; explicit state |
| Anchor added/removed mid-cycle | Defined behaviour, no use-after-free |
| Cycle time budget exceeded | Reported, not silently absorbed |

### 4.6 Calibration store / codegen

| Case | Required behaviour |
| --- | --- |
| BSSID not in table | Explicit "uncalibrated", not offset 0 silently |
| Empty table | Init fails loudly |
| Duplicate BSSID in CSV | Codegen rejects with a clear error |
| Malformed CSV (missing column, bad number) | Codegen fails; must not emit a half-valid header |
| Offset outside `int16_t` range | Rejected — the hardware API takes `int16_t` cm |

### 4.7 CSV protocol (`services/protocols/ftm_csv`)

| Case | Required behaviour |
| --- | --- |
| Output buffer too small | Truncation reported, never overflowed |
| Failed sample (no measurement) | Emits a row with non-zero status and empty fields — dropouts must be visible, not hidden |
| Field containing a separator | Escaped or rejected |

## 5. E2E test requirements (L3)

E2E tests **run autonomously** — no human in the loop.

- Both boards are permanently connected: **COM3** and **COM4**.
- Tests must build, flash, and run without manual steps.
- Every E2E test file starts with a **"How to run"** block giving the exact
  command.
- Assertions on distance use a **tolerance band plus a minimum sample count** —
  never a single reading, because of drift (§8 of findings).
- Tests must assert on `valid/total` ratio, not just on a distance value.

Skeleton the phase docs should follow:

```
tests/e2e/
├── conftest.py            # fixtures: dut_responder (COM3), dut_initiator (COM4)
├── test_smoke.py          # boots, roles start, responder advertises FTM
├── test_session.py        # initiator completes a session, valid ratio >= 0.8
├── test_calibration.py    # offset applied -> reported distance shifts linearly
└── README.md              # how to run, expected duration, troubleshooting
```

## 6. Manual integration test (L5)

One test requires physical movement and is therefore **operator-executed**.

Requirements:
- Prints **numbered, unambiguous instructions** to the operator ("place the
  initiator at 1 m, press ENTER; walk slowly to 5 m over ~30 s, press ENTER").
- Records continuously throughout, including during movement.
- Produces two artefacts:
  1. A **chart** (PNG) of distance vs. time with the annotated phases.
  2. A **machine-readable summary** (JSON) — per-phase mean, σ, sample count,
     valid ratio, RSSI, and detected transitions.
- The JSON exists so an **AI can evaluate the result** without seeing the chart.
  It must contain enough to judge: did the measured distance track the
  commanded movement, monotonically, within tolerance?
- Marked `@pytest.mark.manual` and excluded from the autonomous run by default.

## 7. CI-readiness

Not required now, but do not preclude it:
- L1 and L4 must run with no hardware attached.
- L2/L3/L5 must be selectable by marker so a hardware-less runner can skip them.
