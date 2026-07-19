# Phase 5 — E2E Suite & Human-in-Loop Movement Test

| | |
| --- | --- |
| **Status** | Not started |
| **Depends on** | Phase 3, Phase 4 |
| **Blocks** | Nothing — final phase |
| **Read first** | `docs/PLAN.md` §1–6, `docs/TESTING.md` §5–6, `docs/HARDWARE_FINDINGS.md` §7–8 |

---

## Objective

Two things:

1. **Consolidate the autonomous E2E suite** into one runnable, documented set.
2. **Build the operator-driven movement test** — the only test that requires a
   human, because it requires physically moving a board.

---

## Part 1 — Autonomous E2E suite

Earlier phases each contributed E2E tests. This part makes them a coherent
suite: one command, documented duration, clear failures.

**Deliverables**

```
tests/e2e/
├── conftest.py             # from Phase 0: dut_responder COM3, dut_initiator COM4
├── test_smoke.py           # Phase 3
├── test_session.py         # Phase 3
├── test_role_strategy.py   # Phase 3
├── test_calibration.py     # Phase 2
├── test_multi_station.py   # Phase 4
└── README.md               # HOW TO RUN — exact commands, duration, troubleshooting
```

**Requirements**

- `pytest -m "not manual"` runs the whole suite with **no human interaction**.
- The README states the **expected wall-clock duration** — sessions are ~1.5 s
  each (findings §2), so a suite doing hundreds of sessions takes real time.
  An agent that does not know this will assume a hang.
- Every distance assertion uses a **tolerance band + minimum sample count**.
  Findings §8 documents drift of 1.23 m → 0.10 m at a fixed setup; a tight
  single-sample assertion **will** flake and then be "fixed" by someone loosening
  it thoughtlessly.
- Failures must say **which DUT** and **what was expected**.
- Missing/disconnected board → clear message, not a hang.

**Troubleshooting section must cover** (all real, previously hit):

| Symptom | Cause |
| --- | --- |
| Serial writes time out, but boot logs appear | Firmware missing `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` (findings §1) |
| AP state lost between steps | Opening a serial port resets the board — hold both ports in one process |
| All readings 0.00 m | Boards too close; zero-distance clamp (findings §4) |
| "success" but nonsense values | valid ratio collapsed to 2–3/30 (findings §6) |
| `export.ps1` fails | Microsoft Store `python` alias shadows IDF python (PLAN §6) |
| Negative offset parsed as a flag | Use `--offset=-200`, not `-o -200` |

---

## Part 2 — Movement integration test (operator-executed)

**This test cannot be automated — it requires a human to physically move a
board.** It is marked `@pytest.mark.manual` and excluded from the autonomous run.

Its purpose: prove the whole stack tracks **real motion**, which no static test
can show. It is also the test that distinguishes genuine motion from the drift
in findings §8 — the single most important open question about this system.

### Deliverables

```
tests/manual/
├── test_movement.py        # the operator-driven test
├── analyse_movement.py     # transcript -> chart + JSON summary
├── output/                 # generated artefacts
└── README.md               # operator instructions
```

### Protocol

The test **prints numbered, unambiguous instructions** and waits for ENTER
between phases. Suggested sequence:

```
1. Place the anchor (COM3) at a fixed point. Press ENTER.
2. Place the initiator (COM4) at 1.0 m from the anchor, line of sight.
   Measure with a tape. Enter the measured distance in cm, then ENTER.
3. HOLD STILL for 60 seconds.                      [baseline / drift capture]
4. Walk SLOWLY to 5.0 m over about 30 seconds.     [ramp]
5. HOLD STILL for 60 seconds. Enter measured distance in cm.
6. Walk SLOWLY back to 1.0 m over about 30 seconds.
7. HOLD STILL for 60 seconds.
```

Phases 3, 5 and 7 are static; the two 60 s static blocks bracketing the movement
are what let the analysis separate **drift** from **motion**.

Recording runs continuously through all phases, including the walks.

### Artefacts

**1. Chart** — `output/movement_<timestamp>.png`: distance vs. time, raw and
filtered, with phase boundaries annotated and the operator's tape-measured
reference distances drawn as horizontal lines. RSSI and valid-ratio on a second
axis.

**2. Machine-readable summary** — `output/movement_<timestamp>.json`. **This is
what an AI evaluates**, so it must be self-sufficient — the evaluator will not
see the chart:

```jsonc
{
  "phases": [
    {
      "name": "static_1m",
      "reference_cm": 100,
      "samples": 40, "valid_ratio": 0.97,
      "mean_cm": 122, "median_cm": 120, "stddev_cm": 28,
      "min_cm": 75, "max_cm": 165,
      "rssi_mean": -52,
      "drift_cm_per_min": -8.4        // slope within the static phase
    }
    // ... ramp_up, static_5m, ramp_down, static_1m_return
  ],
  "transitions": [
    { "from": "static_1m", "to": "static_5m",
      "expected_delta_cm": 400, "measured_delta_cm": 372,
      "monotonic": true, "monotonic_violations": 2 }
  ],
  "verdict_inputs": {
    "tracked_movement": true,
    "static_drift_exceeds_movement": false,
    "any_phase_valid_ratio_below_0_8": false
  }
}
```

### Evaluation criteria (for whoever/whatever reads the JSON)

The test **does not pass/fail itself** — it produces evidence. State these
criteria in the README so evaluation is consistent:

1. **Tracking:** `measured_delta_cm` for each transition within ±30 % of
   `expected_delta_cm`.
2. **Monotonicity:** ramp phases largely monotonic; a few violations are
   expected given the observed 0.75–1.65 m spread at a fixed 1.2 m (findings §7).
3. **Drift vs. motion:** `drift_cm_per_min` in static phases must be **small
   compared to** the movement delta. If static drift rivals the 400 cm movement,
   the system is not usable for navigation and that is the headline result.
4. **Quality:** no phase with valid ratio < 0.8 (findings §6).
5. **Return:** final static phase should agree with the first within tolerance —
   catches accumulating bias.

**An honest negative result is a valid outcome of this phase.** If drift
dominates, say so plainly; do not tune until the chart looks good.

### Requirements

- Instructions unambiguous — the operator should never wonder what "slowly"
  means (give the duration).
- Operator enters **tape-measured** ground truth; never assume the nominal.
- Tolerate operator timing sloppiness — segment by the ENTER markers, not by
  assumed wall-clock.
- If the operator aborts mid-run, partial artefacts must still be written.

### Required tests for the analysis code

`analyse_movement.py` is ordinary code and gets ordinary tests (L4 pytest),
using **recorded transcripts** as fixtures:

| Case | Expected |
| --- | --- |
| Clean ramp | Transition detected, delta correct |
| Static-only recording | No transitions; not a crash |
| Drift-dominated recording (from findings §8 data) | Flagged: `static_drift_exceeds_movement: true` |
| Phase with all-invalid samples | Phase marked invalid; not mean-of-nothing |
| Operator aborted mid-run | Partial JSON + chart written |
| Non-monotonic ramp | Violations counted, not silently smoothed |
| Missing operator reference | Handled; phase reported without `reference_cm` |

## Acceptance criteria

- [ ] `pytest -m "not manual"` runs the full autonomous suite green.
- [ ] E2E README documents commands, duration, and the troubleshooting table.
- [ ] `pytest -m manual` runs the movement test with clear operator prompts.
- [ ] A real operator run produces both a PNG and a self-sufficient JSON.
- [ ] Analysis code tested against recorded transcripts including the
      drift-dominated case.
- [ ] README states the evaluation criteria so results are judged consistently.

## Open questions

- Should the movement test also sweep **height** (z) once ≥4 anchors exist? Out
  of scope at 2 boards; note it for later.
