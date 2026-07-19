# Phase 3 — Definitive Layered Firmware

| | |
| --- | --- |
| **Status** | Not started |
| **Depends on** | Phase 0 (test harness), Phase 2 (calibration CSV schema) |
| **Blocks** | Phase 4, Phase 5 |
| **Read first** | `docs/PLAN.md` (all), `docs/ARCHITECTURE.md` (all), `docs/HARDWARE_FINDINGS.md` (all), `docs/TESTING.md` §3–4 |

---

## Objective

The production firmware: layered, role-selected by Strategy pattern, calibrated
from the Phase 2 table, and fully unit-tested.

**This phase is large. It is split into sub-phases 3a–3e, each independently
assignable.** Sub-phases are strictly ordered.

## Governing constraints

From `docs/PLAN.md` §5 — an agent violating one of these should **stop and
flag**, not work around:

1. `domain/` includes **zero** ESP-IDF headers. It compiles natively on the PC.
2. `esp_err_t` must not appear in any `domain/` or `services/` public header.
3. Role selection uses the **Strategy vtable**. The only role `#ifdef` lives in
   the CMake source list and in `ftm_role_get()`.
4. Empty layers (`drivers/devices/`) are created with a `README.md` and **not**
   deleted as unused.
5. Design for **N anchors**. Two boards is the test fixture.
6. No hardcoded calibration constants.
7. Every feature has worst-case unit tests, not just happy path.

---

## Sub-phase 3a — Skeleton + `domain/types`

**Deliverables**

```
components/domain/
├── CMakeLists.txt
└── types/include/
    ├── ftm_result.h        result/error enum; the shared vocabulary
    ├── ftm_measurement.h   one FTM sample + quality metrics
    ├── ftm_station.h       anchor identity (BSSID key) + position
    ├── ftm_calibration.h   calibration record
    └── ftm_role.h          the strategy vtable (see ARCHITECTURE §3)
components/services/CMakeLists.txt        (+ empty middleware/, protocols/)
components/drivers/CMakeLists.txt
components/drivers/devices/README.md      (why empty — ARCHITECTURE §5)
```

**`ftm_measurement_t` must carry the quality fields**, not just a distance —
`valid_count`, `total_count`, `rtt_raw_ns`, `rssi_dbm`, `status`. Findings §6
shows status alone cannot detect a bad measurement.

Represent distance **signed** (`int32_t` cm). The hardware's `uint32_t` wraps on
over-correction (findings §4); the domain type must not inherit that hazard.

**Tests:** type invariants, enum-to-string for every value including an invalid
one, struct packing assumptions if any.

---

## Sub-phase 3b — `domain/core` (pure logic)

The highest-value testing target in the project: pure C, no hardware, all the
subtle behaviour.

**Deliverables**

```
components/domain/core/
├── include/
│   ├── ftm_distance.h        rtt -> distance, calibration application
│   ├── ftm_filter.h          rolling median, EMA, outlier rejection
│   └── ftm_trilateration.h   N-anchor 3D solve
└── src/
```

**`ftm_distance`** — convert `rtt_raw_ns` to distance, apply calibration offset.
Must honour: inverted offset sign (`reported ≈ true − offset`, findings §5),
signed result, explicit error rather than wrap on over-correction.

**`ftm_filter`** — must distinguish *motion* from *drift*. Findings §8 documents
a 1.23 m → 0.10 m shift at a fixed setup. A filter that silently tracks this
reports the node teleporting. At minimum: rolling median + a stability/quality
signal the caller can act on.

**`ftm_trilateration`** — N anchors → 3D position + residual. Degenerate
geometry must be **detected and reported**, never solved into garbage.

**Tests: all of `docs/TESTING.md` §4.1, §4.2, §4.3.** This sub-phase is not done
until every row in those three tables has a test. Use the real recorded values
from findings §7 and §8 as fixtures.

---

## Sub-phase 3c — `drivers/peripherals/wifi`

The only layer allowed to touch ESP-IDF.

**Deliverables**

```
components/drivers/peripherals/wifi/
├── include/
│   ├── wifi_iface.h    init, mode, scan, AP config
│   └── wifi_ftm.h      FTM initiator/responder operations
├── src/
└── test_apps/          L2 on-target Unity tests
```

**Must get right** (each is a documented hazard):

- **Drain the report on every path** — success, failure, timeout. Upstream leaks
  here (findings §9). Explicit test required.
- Translate `esp_err_t` → `ftm_result_t` at the boundary.
- Never return a pointer into a buffer the next scan frees (findings §9).
- Cache BSSID + channel; expose a scan operation but **never scan per
  measurement** (~2.5 s, findings §2).
- Support unassociated FTM — it works and is the default (findings §2).
- Expose `valid_count` / `total_count` from the report.
- Expose `rtt_raw`, not just `rtt_est` (findings §3).

**Tests:** L2 on-target Unity, covering `docs/TESTING.md` §4.4. The report-leak
test should assert heap is unchanged across many failed sessions.

---

## Sub-phase 3d — `services/` + role strategies

**Deliverables**

```
components/services/
├── middleware/
│   ├── include/
│   │   ├── ftm_scheduler.h      measurement loop, anchor round-robin
│   │   ├── ftm_calib_store.h    calibration lookup (ARCHITECTURE §6)
│   │   └── ftm_role.h           ftm_role_get()
│   └── src/
│       ├── ftm_role.c
│       ├── ftm_role_initiator.c   compiled iff CONFIG_FTM_ROLE_INITIATOR
│       └── ftm_role_responder.c   compiled iff CONFIG_FTM_ROLE_RESPONDER
└── protocols/
    ├── include/ftm_csv.h
    └── src/
main/
├── app_main.c        role-agnostic; see ARCHITECTURE §3
└── Kconfig.projbuild role choice, SSID, channel, timings
```

`app_main.c` must contain **no role logic** — get the strategy, drive the
lifecycle, nothing else.

Services depend on **driver interfaces**, so CMock can substitute a mock
`wifi_ftm.h` and the scheduler becomes host-testable. This is the payoff for the
layering; if the scheduler cannot be host-tested, the dependency direction is
wrong.

**Tests:** `docs/TESTING.md` §4.5, §4.6, §4.7, plus strategy lifecycle tests
with an injected fake strategy — including failure injected at `init`, `start`,
and `run`.

---

## Sub-phase 3e — Calibration table integration

**Deliverables**

```
tools/gen_calibration_table.py     CSV -> generated C header
components/domain/types/include/ftm_calibration_table.h   (GENERATED)
```

Consumes the Phase 2 CSV schema exactly as handed off. Emits a header banner
`/* GENERATED — do not edit by hand. Source: <csv> */`.

**Codegen must fail loudly** on: duplicate BSSID, malformed row, missing column,
offset outside `int16_t`. It must **never emit a half-valid header** — a partial
write here produces a firmware that is silently miscalibrated.

**Tests:** `docs/TESTING.md` §4.6 (L4 pytest for the generator, L1 for the
lookup API), including a golden-file test of generated output.

---

## E2E tests for this phase (L3, autonomous)

```
tests/e2e/
├── test_smoke.py         both roles boot; responder advertises [FTM Responder]
├── test_session.py       initiator completes sessions; valid ratio >= 0.8
└── test_role_strategy.py responder build and initiator build behave distinctly
```

Assertions use **tolerance bands and minimum sample counts**, never a single
reading (findings §8).

## Acceptance criteria

- [ ] `domain/` compiles natively with no ESP-IDF headers — enforced by the L1
      build, not just by convention.
- [ ] No `esp_err_t` in any `domain/`/`services/` public header.
- [ ] Only one role `#ifdef` in CMake + `ftm_role_get()`; none in business logic.
- [ ] `drivers/devices/README.md` exists and explains itself.
- [ ] Every row of `docs/TESTING.md` §4.1–4.7 has a corresponding test.
- [ ] Report-leak test proves heap stability across repeated failed sessions.
- [ ] Both boards run the definitive firmware; E2E suite green.
- [ ] Calibration table generated from a real Phase 2 CSV.

## Open questions

- Should the initiator also expose a console for field debugging, or stay
  headless? Headless is simpler and the bench firmware (Phase 1) covers manual
  probing. Recommend headless; flag if the reviewer disagrees.
- Filter choice (median window size, EMA alpha) should be **Kconfig-tunable**
  and its default justified by measured data, not guessed.
