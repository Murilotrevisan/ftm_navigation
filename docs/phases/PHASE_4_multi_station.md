# Phase 4 — Multi-Station Scaling & Trilateration

| | |
| --- | --- |
| **Status** | Not started |
| **Depends on** | Phase 3 |
| **Blocks** | Phase 5 (movement test) |
| **Read first** | `docs/PLAN.md` §1–5, `docs/ARCHITECTURE.md` §4, `docs/HARDWARE_FINDINGS.md` §2, §8 |

---

## Objective

Turn "one initiator measures one responder" into "one initiator measures N
anchors and computes a 3D position".

## The hardware reality

**Only 2 ESP32-C3 boards exist.** A 3D fix needs ≥ 4 non-coplanar anchors.

This phase therefore delivers a system that is **correct for N anchors and
validated at N=1 on real hardware**, with N≥4 validated in simulation against
the same code path. That is an honest limit, not a shortcoming to paper over.

**Do not fake extra anchors on hardware** (e.g. by pretending one responder is
several). Do not report simulated results as hardware results.

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
components/services/middleware/src/ftm_anchor_table.c
components/services/middleware/include/ftm_anchor_table.h
tools/sim/
├── simulate_anchors.py       N-anchor geometry -> synthetic measurements
└── README.md
tests/sim/
└── test_trilateration_nd.py  N=4..8, noise, degenerate geometries
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
4. **Simulator** — generate synthetic measurements from a known geometry with
   configurable noise, including the 15 cm quantisation and the drift character
   from findings §8. This is how N≥4 gets exercised without hardware.
   - The simulator must feed **the same domain code** as the firmware. A
     simulator with its own copy of the math tests nothing.
5. **Document the N=1 hardware limit** plainly in the README.

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

## E2E test (L3, autonomous, N=1)

`tests/e2e/test_multi_station.py`:
- One responder (COM3), one initiator (COM4).
- Assert the scheduler completes cycles, produces a range for the single anchor,
  and correctly reports **"insufficient anchors for a 3D fix"** rather than
  emitting a position.
- That negative assertion is the valuable one at N=1: it proves the system fails
  honestly rather than inventing a fix.

## Acceptance criteria

- [ ] Anchor table driven by the generated calibration table; no hardcoded
      anchors.
- [ ] Scheduler round-robins and marks partial cycles.
- [ ] Trilateration returns position **and residual**, detects degeneracy.
- [ ] Simulator exercises the **same** domain code as firmware.
- [ ] All §4.3 / §4.5 worst cases tested; N=4..8 covered in simulation.
- [ ] E2E at N=1 proves honest failure to produce a 3D fix.
- [ ] README states the ~1.5·N second cycle time and the 2-board limit.

## Open questions

- Should the initiator weight ranges by RSSI or valid-ratio in the solve?
  Physically motivated, but adds a tuning parameter that cannot be validated
  with 2 boards. Recommend deferring until ≥4 boards exist.
- Is a Kalman/particle filter over successive fixes wanted, or is per-cycle
  trilateration enough for this feasibility bench? Recommend per-cycle only for
  now — drift (findings §8) would need characterising before a motion model is
  trustworthy.
