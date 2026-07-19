# Testing Strategy

> **STATUS: SETTLED.** The framework question is closed — see §2. Everything in
> this document runs inside the container described in `docs/CONTAINER.md`.

---

## 1. Test levels

| Level | Scope | Framework | Runs where | Speed |
| --- | --- | --- | --- | --- |
| **L1a Unit — host** | `domain/types`, `domain/core` | **Ceedling** (Unity + CMock) | Container | < 1 s |
| **L1b Unit — host** | `services/*`, domain+services integration | **ESP-IDF `linux` target** + Unity + CMock | Container | seconds |
| **L2 Unit — target** | `drivers/peripherals/wifi` | Unity (ESP-IDF `test_apps`) | ESP32-C3 | ~30 s |
| **L3 E2E — two boards** | Full firmware, both roles | pytest + pytest-embedded | **Windows host, venv** | minutes |
| **L4 Host tools** | calibrator, codegen, analysis | pytest | **Windows host, venv** | seconds |
| **L5 Manual integration** | Physical movement → chart | pytest, human-in-loop | **Windows host, venv** | ~10 min |
| **Lsim Simulation** | 3D trilateration, N≥4 anchors | Ceedling | Container | seconds |

Build and host unit tests run **in the container**; anything touching the boards
runs **on Windows in a venv**. See `docs/CONTAINER.md`.

The layering in `docs/ARCHITECTURE.md` is what makes L1 and Lsim possible:
`domain/` has zero ESP-IDF dependencies, so the bulk of the logic — including
all the 3D positioning maths — is testable with no board attached.

## 2. Framework decision — SETTLED

**Both Ceedling and ESP-IDF's Linux target, together — not one substituting the
other.** They have distinct jobs.

### L1a — Ceedling (Unity + CMock) → `domain/`

- Sub-second feedback on pure logic, which is where the interesting worst-case
  behaviour lives: clamp, sign inversion, overflow, degenerate geometry.
- CMock **generates C mocks directly from headers**, so a mock cannot silently
  drift from the real interface.
- Ruby lives **in the container image only** — never installed on the PC.

### L1b — ESP-IDF `linux` target → `services/`

Verified present in the installed ESP-IDF v5.5.2:

| Component | Path |
| --- | --- |
| Linux target toolchain | `tools/cmake/toolchain-linux.cmake` |
| Linux target port | `components/esp_system/port/soc/linux` |
| Unity | `components/unity` |
| CMock | `components/cmock` (bundled) |

`services/` sits inside the IDF component system and depends on driver
interfaces. Testing it through IDF's own build exercises the **real component
dependency graph and the real Kconfig wiring** — including the role-strategy
source selection — which a standalone Ceedling project cannot see.

### The division rule

> **Each module has exactly ONE authoritative host test suite.** `domain/` is
> Ceedling's. `services/` is the Linux target's. **Never test the same module in
> both.**

This matters: duplicated suites drift, then disagree, and the disagreement gets
resolved by weakening whichever one is inconvenient — which
`docs/WORKFLOW.md` §3 forbids anyway. The two systems are complementary in
scope, not redundant in coverage.

### L2 / L3 / L4 / L5

- **L2** — Unity via ESP-IDF `test_apps`. Anything touching `esp_wifi` must run
  on silicon; there is no meaningful way to fake the FTM hardware timing path.
- **L3 / L5** — pytest + `pytest-embedded-idf` + `pytest-embedded-serial-esp`,
  in the **Windows venv**. First-class multi-DUT support (`--count 2`) matches
  the two-board topology; the boards become `dut[0]` / `dut[1]` rather than
  hand-rolled pyserial plumbing.
- **L4** — plain pytest, same venv.

### Coverage — gcovr

`gcovr` runs in the container over the L1a Ceedling suite (and L1b where
practical), emitting HTML + XML to `build_container/coverage/`.

**Proposed thresholds** (adjustable — flagged for review, not blocking):

| Target | Line | Branch |
| --- | --- | --- |
| `domain/core` | ≥ 90 % | ≥ 85 % |
| `domain/types` | ≥ 80 % | — |
| `services/` | ≥ 80 % | ≥ 70 % |

`domain/core` is held highest because it is pure, fully reachable, and carries
the maths that a wrong answer silently corrupts.

Coverage is a **floor, not a goal**. High coverage with only happy-path
assertions still fails §3.

### Rejected, with reasons

| Option | Why not |
| --- | --- |
| **gmock / gtest** | C++ frameworks; the firmware is C. CMock generates C mocks from the real headers with far less ceremony. |
| **Hand-written fakes instead of CMock** | Drift. A fake not regenerated from the header silently diverges when the interface changes, and the test keeps passing. |
| **Everything on-target** | Too slow per-edit; kills the feedback loop that makes worst-case testing practical. |
| **Ceedling *or* Linux target** | Rejected in favour of both, with the strict division rule above. |

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

### 4.7 Telemetry protocol (`services/protocols/ftm_csv`)

Spec: `docs/PROTOCOL.md`. Encoder tests live at L1b, decoder tests at L4.

| Case | Required behaviour |
| --- | --- |
| Output buffer too small | Truncation reported, never overflowed |
| Failed sample (no measurement) | Emits `$FTMRNG` with non-zero status and empty measurement fields — dropouts visible, not hidden |
| Field containing a separator | Escaped or rejected |
| `fix_quality = 0/1` | Position fields **empty**, never `0,0,0` — zero is a valid coordinate |
| `fix_quality >= 2` | Position fields populated and `residual_cm` present |
| Checksum | Correct XOR over `$`..`*` exclusive; decoder **rejects and counts** a bad checksum rather than silently dropping |
| Truncated sentence mid-field | Rejected, no partial parse |
| Unknown trailing fields | **Ignored, not an error** — append-only evolution (PROTOCOL §1 rule 5) |
| `num_anchors` disagrees with `$FTMRNG` count in the cycle | Detected and reported by the decoder |
| Negative `dist_cm` | Parsed as signed; must not wrap (`HARDWARE_FINDINGS.md` §4) |
| Stale position after quality drops below 2 | Decoder must clear it, not retain |

### 4.8 Range-only fallback (`services/middleware`, see PHASE_4)

Fewer than 4 anchors means no 3D fix. The system falls back to reporting per-
station linear distances (`docs/ARCHITECTURE.md` §4).

| Case | Required behaviour |
| --- | --- |
| 0 anchors ranged | Explicit "no data" state; not an empty success |
| 1–3 anchors ranged | `RANGE_ONLY` result listing `(station_id, distance_cm)` per anchor |
| ≥4 anchors but coplanar | `RANGE_ONLY`, with degeneracy as the stated reason — **not** a bogus 3D fix |
| ≥4 anchors, good geometry | `POSITION_3D` result |
| Mode changes between cycles | Consumers must handle the transition; no stale 3D fix retained after dropping below 4 |
| A station drops out mid-run | Falls back to `RANGE_ONLY` cleanly |

The mode must be **explicit in the output**, never inferred by the consumer from
whether a position field happens to be populated.

## 5. E2E test requirements (L3)

E2E tests **run autonomously** — no human in the loop.

- Both boards are permanently connected, and **physically fixed 1.00 m apart**
  (see `docs/HARDWARE_FINDINGS.md` §10). This is the standing test fixture:
  tests may assert against a 1 m ground truth without an operator.
- Tests must build, flash, and run without manual steps.
- Every E2E test file starts with a **"How to run"** block giving the exact
  command.
- Assertions on distance use a **tolerance band plus a minimum sample count** —
  never a single reading, because of drift (§8 of findings).
- Tests must assert on `valid/total` ratio, not just on a distance value.

Skeleton the phase docs should follow:

```
tests/e2e/
├── conftest.py            # fixtures: dut_responder, dut_initiator (by MAC, not port)
├── test_smoke.py          # boots, roles start, responder advertises FTM
├── test_session.py        # initiator completes a session, valid ratio >= 0.8
├── test_calibration.py    # offset applied -> reported distance shifts linearly
├── test_range_only.py     # <4 anchors -> RANGE_ONLY, never a fabricated 3D fix
└── README.md              # how to run, expected duration, troubleshooting
```

Fixtures resolve boards by **MAC address, not port number** — ports re-enumerate
unpredictably, and flashing the wrong role onto the wrong board produces a very
confusing failure (`docs/CONTAINER.md` §5).

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
