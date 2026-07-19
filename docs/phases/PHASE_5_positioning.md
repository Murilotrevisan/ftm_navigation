# Phase 5 — Positioning: Host-First, Then Target

| | |
| --- | --- |
| **Status** | Not started |
| **Depends on** | Phase 3, Phase 4 (protocol + logs + replay) |
| **Blocks** | Phase 6 (E2E and movement test) |
| **Branches** | `phase-5a/positioning-host`, then `phase-5b/positioning-target` |

---

## Start here

1. **Read `docs/AGENT_BRIEF.md` first**, then the documents it lists, then this
   one in full. Also read `docs/ARCHITECTURE.md` §6 (positioning modes) and
   `docs/PROTOCOL.md` §7 (replay).
2. **Two branches, strictly ordered — host first:**
   ```bash
   git worktree add ../ftm-phase-5a -b phase-5a/positioning-host
   cd ../ftm-phase-5a
   ```
   `phase-5b/positioning-target` starts only after 5a is merged.
3. **Requires Phases 3 and 4** — 5a is driven by Phase 4's `.ftmlog` replay.
4. **Done means:** per sub-phase — acceptance criteria ticked, full suite green,
   report written to `docs/reports/phase-5<x>-positioning-<host|target>.md`,
   branch left for human review.

**Do not write a host prototype to "port" later.** Ported code is different
code and proves nothing. One source file in `domain/core/`, compiled natively in
5a and for the target in 5b.

With 2 boards this phase produces **no 3D fix on hardware, ever** — and the
valuable E2E assertion is exactly that it reports `RANGE_ONLY` honestly instead
of inventing one.

---

## Objective

Turn "one initiator measures one responder" into "one initiator measures N
anchors and computes a 3D position".

## The method: host first, target second

**The 3D algorithm is developed and proven on the host against recorded logs
before a line of it is compiled for the target.** This is the whole reason
Phase 4 built the protocol, `.ftmlog` capture, and the replay tool.

```
Phase 4 logs  -->  host replay  -->  the SAME domain/core code  -->  position
                                              |
                                    proven, then compiled for target
                                              |
                                     firmware starts emitting NAV-POSITION
```

Two sub-phases, strictly ordered:

### 5a — Host

- Solver lives in `components/domain/core/` (pure C, zero ESP-IDF — this is what
  makes it compile both natively and for the target).
- Driven by `tools/proto/ftm_replay.py` over recorded `.ftmlog` files and over
  simulated N≥4 geometries.
- Validated entirely in the container. **No board involved.**
- Ends when the solver is correct and every worst case in
  `docs/TESTING.md` §4.3 passes.

### 5b — Target

- The **same source file**, now compiled into the firmware.
- Firmware begins emitting `NAV-POSITION` — but only when `fix_quality >= 2`,
  which with 2 boards **never happens**.
- So 5b is validated by: the code builds for target, runs, and correctly
  continues to emit **no** `NAV-POSITION`.

**Do not write a separate host implementation.** A host prototype that is later
"ported" tests nothing — the ported code is different code. One source, two
compilation targets.

## The hardware reality, and the fallback rule

**Only 2 ESP32-C3 boards exist.** A 3D fix needs ≥ 4 non-coplanar anchors.

The system therefore has two explicit modes (`docs/ARCHITECTURE.md` §4):

```c
FTM_FIX_NONE         /* no usable ranges this cycle         */
FTM_FIX_RANGE_ONLY   /* < 4 anchors, or degenerate geometry */
FTM_FIX_POSITION_3D  /* >= 4 non-coplanar anchors           */
```

> **Rule: fewer than 4 usable anchors → report `RANGE_ONLY`**, a list of
> `(station_id, distance_cm)` pairs. No position is computed and none is
> guessed.

`RANGE_ONLY` is a **useful product state, not an error path.** Per-station
distances are a valid reference reading, they let the visualisation be built and
exercised now, and they make the system honest — it reports what it measured
instead of inventing a coordinate.

All 3D logic is nonetheless **fully implemented and fully validated in host
simulation** (Lsim, in the container, no hardware). It is correct and tested
before four boards ever exist; the moment two more arrive, `POSITION_3D`
engages with no code change.

**Do not fake extra anchors on hardware** (e.g. pretending one responder is
several). **Do not report simulated results as hardware results.**

## Key constraints

| Constraint | Value | Ref |
| --- | --- | --- |
| Session duration | ~1.5 s | findings §2 |
| Full cycle over N anchors | ~1.5·N seconds | ARCHITECTURE §4 |
| 4 anchors → one 3D fix | ~6 s | derived |
| Anchor identity key | **BSSID**, not SSID | ARCHITECTURE §4 |
| All anchors on one channel | avoids mid-cycle channel hop | ARCHITECTURE §4 |
| Distance quantisation | 15 cm — accepted | findings §3 |
| Drift | real and large | findings §8 |

The ~6 s fix rate is a **known, accepted limitation**. Record it in the README.
Do not silently optimise it away by cutting `frm_count` without measuring the
accuracy cost.

## Deliverables

```
components/domain/core/src/ftm_trilateration.c    (completed from 3b)
components/domain/types/include/ftm_fix.h          fix mode + result union
components/services/middleware/src/ftm_anchor_table.c
components/services/middleware/include/ftm_anchor_table.h
tools/sim/
├── simulate_anchors.py       N-anchor geometry -> synthetic measurements
└── README.md
tools/viz/
├── viz.py                    live visualisation, BOTH modes
└── README.md
tests/sim/
└── test_trilateration_nd.c   N=4..8, noise, degenerate geometries (linux target)
```

## Tasks

1. **Anchor table** — BSSID → (position, calibration offset, last measurement,
   staleness). Configured from the generated calibration table (Phase 3e), which
   is why `x_cm,y_cm,z_cm` exist in the Phase 2 CSV schema.
2. **Round-robin scheduler** — cycle through anchors, one FTM session each,
   assemble a range set per cycle.
   - A cycle with a missing anchor completes and is **marked partial**.
   - Stale ranges must never be silently reused. Staleness is explicit.
3. **Trilateration** — N ranges + N positions → position + residual. Report the
   residual; it is the caller's only signal that the fix is inconsistent.
4. **Mode selection** — implement the `RANGE_ONLY` / `POSITION_3D` decision.
   Degenerate geometry with ≥4 anchors also yields `RANGE_ONLY`, with the
   reason stated. Dropping below 4 anchors must not leave a stale 3D fix visible.
5. **Simulator** — generate synthetic measurements from a known geometry with
   configurable noise, including the 15 cm quantisation and the drift character
   from findings §8. This is how N≥4 gets exercised without hardware.
   - The simulator must emit **real `.ftmlog` files in the Phase 4 binary
     format**, so simulated and recorded data flow through an identical path.
   - It must feed **the same domain code** as the firmware. A simulator with its
     own copy of the maths tests nothing.
6. **Visualisation** (`tools/viz/`) — must render **both** modes:
   - `RANGE_ONLY`: per-station distance readout — station label, distance, valid
     ratio, RSSI. A radial/bar layout works; the point is to see live numbers per
     anchor with 2 boards **today**.
   - `POSITION_3D`: 3D scatter of anchors + the estimated position, with the
     residual shown.
   - Mode is displayed explicitly. The viewer must never be able to mistake a
     range-only reading for a position fix.
   - Feed it from the simulator as well as from live serial, so the 3D view is
     demonstrable and reviewable before four boards exist.
7. **Document the hardware limit** plainly in the README: 2 boards → N=1 anchor
   → `RANGE_ONLY` only. 3D is simulation-validated, not hardware-validated.

## Required tests

All of `docs/TESTING.md` §4.3 and §4.5, plus:

| Case | Expected |
| --- | --- |
| N=4 ideal geometry, no noise | Position recovered to < 1 cm |
| N=4 with 15 cm quantisation | Recovered within a stated bound; document it |
| N=4 coplanar | Degeneracy detected and reported |
| N=3 | `FTM_ERR_INSUFFICIENT_ANCHORS` for a 3D fix |
| N=8 with one wild outlier | Outlier rejected or residual clearly elevated |
| One anchor stale | Excluded; cycle marked partial |
| All anchors stale | No fix; explicit state |
| Anchor removed mid-cycle | Defined behaviour, no use-after-free |
| Ranges inconsistent (no intersection) | Best-fit **plus** high residual, not silent nonsense |
| Duplicate anchor positions | Rejected before the solve |

Simulation tests must include **noise drawn from the real measured spread**
(findings §7: 0.75–1.65 m at a 1.2 m true distance), not an optimistic
assumption.

Plus all of `docs/TESTING.md` §4.8 (range-only fallback).

## E2E test (L3, autonomous, N=1)

`tests/e2e/test_range_only.py`:
- One responder, one initiator, **fixed 1.00 m apart** (findings §10).
- Assert the scheduler completes cycles and produces a range for the single
  anchor, with distance within the standing band: mean over ≥60 samples,
  1.00 m ±0.75 m, valid ratio ≥ 0.8.
- Assert the result mode is **`RANGE_ONLY`** and that **no position is emitted**.
- That negative assertion is the valuable one at N=1: it proves the system fails
  honestly rather than inventing a fix.

## Acceptance criteria

**5a — host**

- [ ] Solver lives in `domain/core/`, compiles natively, zero ESP-IDF includes.
- [ ] Proven by replay over **real recorded** `.ftmlog` files from Phase 4.
- [ ] Simulator emits real binary `.ftmlog`; simulated and recorded data share
      one path.
- [ ] All §4.3 / §4.5 / §4.8 worst cases pass; N=4..8 covered.
- [ ] Trilateration returns position **and residual**, detects degeneracy.

**5b — target**

- [ ] The **same source file** compiled into firmware — no second
      implementation.
- [ ] Firmware emits `NAV-POSITION` only when `fix_quality >= 2`.
- [ ] With 2 boards it emits **none**, and E2E proves that.

**Both**

- [ ] Anchor table driven by the generated calibration table; no hardcoded
      anchors.
- [ ] Scheduler round-robins and marks partial cycles.
- [ ] Visualisation renders both modes; 3D demonstrable from simulator input.
- [ ] README states the ~1.5·N cycle time, the 2-board limit, and that 3D is
      **simulation- and replay-validated, not hardware-validated**.
- [ ] Work on `phase-5a/...` and `phase-5b/...` branches; full test output
      reported (`docs/WORKFLOW.md`).

## Deferred, with reasons

Both of these are deferred deliberately. Do not implement them in this phase.

- **Range weighting by RSSI or valid-ratio.** Physically motivated, but it adds
  a tuning parameter that cannot be validated with 2 boards — the weights would
  be fitted to simulation assumptions rather than to hardware. Revisit at
  ≥ 4 boards.
- **Kalman / particle filtering over successive fixes.** A motion model is only
  trustworthy once the drift in `HARDWARE_FINDINGS.md` §8 is characterised;
  applied before that, it would smooth drift and motion together and make the
  two indistinguishable — destroying the very thing Phase 6 sets out to measure.
  Per-cycle trilateration only, for now.
