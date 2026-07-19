# Phase 6 — E2E Suite & Human-in-Loop Movement Test

| | |
| --- | --- |
| **Status** | Not started |
| **Depends on** | Phase 3, Phase 4 (protocol), Phase 5 (positioning) |
| **Blocks** | Nothing — final phase |
| **Branch** | `phase-6/e2e-and-manual` |

---

## Start here

1. **Read `docs/AGENT_BRIEF.md` first**, then the documents it lists, then this
   one in full. Also read `docs/TESTING.md` §5–6 and
   `docs/HARDWARE_FINDINGS.md` §7, §8 and §10 — the drift and the 1.00 m
   fixture drive every assertion here.
2. **Create your worktree:**
   ```bash
   git worktree add ../ftm-phase-6 -b phase-6/e2e-and-manual
   cd ../ftm-phase-6
   ```
3. **Requires Phases 3, 4 and 5.**
4. **Done means:** acceptance criteria ticked, autonomous suite green,
   operator-driven test runnable with clear prompts, report written to
   `docs/reports/phase-6-e2e-and-manual.md`, branch left for human review.

The movement test is **executed by the human operator**, not by you. You build
it, document it, and produce the analysis; you do not run it. It emits evidence
(a chart plus a self-sufficient JSON), and it does **not** pass or fail itself.

**An honest negative result is a valid outcome.** If drift dominates motion, say
so plainly — do not tune until the chart looks good.

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
├── conftest.py             # from Phase 0: boards resolved by MAC, not port
├── test_smoke.py           # Phase 3
├── test_session.py         # Phase 3
├── test_role_strategy.py   # Phase 3
├── test_calibration.py     # Phase 2
├── test_protocol.py        # Phase 4 — framing, checksums, zero NAV-POSITION
├── test_range_only.py      # Phase 5 — RANGE_ONLY, no fabricated position
└── README.md               # HOW TO RUN — exact commands, duration, troubleshooting
```

The movement test records a `.ftmlog` (Phase 4 format), so its analysis reuses
the Phase 4 decoder rather than a second parser.

The movement test requires the operator to **move a board, breaking the fixed
1.00 m fixture** (findings §10). Its README must instruct the operator to
**restore the 1.00 m spacing afterwards**, since the autonomous suite asserts
against it.

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
--- Horizontal sweep ---
1. Place the anchor at a fixed point. Press ENTER.
2. Place the initiator at 1.0 m from the anchor, line of sight, SAME height.
   Measure with a tape. Enter the measured distance in cm, then ENTER.
3. HOLD STILL for 60 seconds.                      [baseline / drift capture]
4. Walk SLOWLY to 5.0 m over about 30 seconds.     [ramp]
5. HOLD STILL for 60 seconds. Enter measured distance in cm.
6. Walk SLOWLY back to 1.0 m over about 30 seconds.
7. HOLD STILL for 60 seconds.

--- Vertical (z) sweep ---
8.  Return the initiator to 1.0 m horizontal, same height. HOLD 60 s.
9.  RAISE the initiator by 1.0 m over about 20 seconds, keeping horizontal
    distance fixed. Enter the measured height change in cm.
10. HOLD STILL for 60 seconds.
11. LOWER it back over about 20 seconds.
12. HOLD STILL for 60 seconds.
```

Static blocks bracket every movement; they are what let the analysis separate
**drift** from **motion**. Recording runs continuously through all phases,
including the walks.

### Why the z sweep is worth doing with 2 boards

It cannot produce a 3D fix — that needs ≥ 4 anchors. What it tests is whether
**range responds to vertical displacement at all**, which is the precondition
for 3D ever working.

Raising the initiator 1.0 m at a fixed 1.0 m horizontal distance changes true
slant range from 1.00 m to about 1.41 m: a 41 cm change, comfortably above the
15 cm quantisation (`HARDWARE_FINDINGS.md` §3) but well inside the observed
per-sample spread (§7). If that change is not detectable, no amount of anchor
geometry will recover height, and that is a decisive negative result worth
knowing before buying two more boards.

Antenna orientation is a plausible confounder — keep the board's orientation
fixed while changing height, and record its orientation in the report.

Expected slant range for the geometry, for the analysis to compare against:

```
d = sqrt(horizontal² + height_change²)
```

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
    { "from": "static_1m", "to": "static_5m", "axis": "horizontal",
      "expected_delta_cm": 400, "measured_delta_cm": 372,
      "monotonic": true, "monotonic_violations": 2 },
    { "from": "static_z0", "to": "static_z1m", "axis": "vertical",
      "height_change_cm": 100, "horizontal_cm": 100,
      "expected_slant_delta_cm": 41, "measured_delta_cm": 33,
      "monotonic": true, "monotonic_violations": 4 }
  ],
  "verdict_inputs": {
    "tracked_horizontal_movement": true,
    "tracked_vertical_movement": true,
    "static_drift_exceeds_movement": false,
    "any_phase_valid_ratio_below_0_8": false,
    "antenna_orientation_note": "board upright, unchanged throughout"
  }
}
```

### Evaluation criteria (for whoever/whatever reads the JSON)

The test **does not pass/fail itself** — it produces evidence. State these
criteria in the README so evaluation is consistent:

1. **Tracking:** `measured_delta_cm` within ±30 % of `expected_delta_cm` for
   horizontal transitions. For the **vertical** sweep compare against
   `expected_slant_delta_cm` (≈41 cm for a 1 m rise at 1 m horizontal) — and
   judge it more leniently, since the expected change is only ~2.7× the 15 cm
   quantisation. A vertical result that is directionally right but noisy is a
   pass; one showing no response at all is the significant finding.
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
| Vertical phases absent (operator stopped after step 7) | Horizontal result still valid and reported |
| Vertical delta below quantisation | Reported as "no vertical response detected", not rounded to zero silently |

## Acceptance criteria

- [ ] `pytest -m "not manual"` runs the full autonomous suite green.
- [ ] E2E README documents commands, duration, and the troubleshooting table.
- [ ] `pytest -m manual` runs the movement test with clear operator prompts.
- [ ] A real operator run produces both a PNG and a self-sufficient JSON.
- [ ] Analysis code tested against recorded transcripts including the
      drift-dominated case.
- [ ] README states the evaluation criteria so results are judged consistently.

## Acceptance additions for the z sweep

- [ ] Operator protocol includes the vertical sweep (steps 8–12).
- [ ] JSON reports vertical transitions against `expected_slant_delta_cm`.
- [ ] Antenna orientation recorded, since it is the main confounder.
- [ ] A run with no vertical response is reported as such, not smoothed away.
