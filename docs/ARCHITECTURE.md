# Architecture

Applies to the **definitive firmware** (Phase 3 onward). Phases 1 and 2 produce
tools under `tools/` and are deliberately exempt.

---

## 1. Layers

Three layers, strictly ordered. **Dependencies point downward only.**

```
┌─────────────────────────────────────────────────────┐
│  main/                 entry point, role selection  │
├─────────────────────────────────────────────────────┤
│  services/                                          │
│    middleware/   orchestration, scheduling, state   │
│    protocols/    serialisation, wire formats        │
├─────────────────────────────────────────────────────┤
│  domain/                                            │
│    types/        data structures, enums, contracts  │
│    core/         pure logic: math, filters, models  │
├─────────────────────────────────────────────────────┤
│  drivers/                                           │
│    peripherals/  wifi (on-chip peripherals)         │
│    devices/      (empty — see §5)                   │
└─────────────────────────────────────────────────────┘
```

### Dependency rules

| Layer | May depend on | Must NOT depend on |
| --- | --- | --- |
| `domain/types` | nothing (C stdlib only) | everything |
| `domain/core` | `domain/types` | services, drivers, ESP-IDF |
| `services/*` | `domain/*`, driver **interfaces** | driver implementations |
| `drivers/*` | `domain/types`, ESP-IDF | services, `domain/core` |
| `main/` | all | — |

**The critical rule: `domain/` must not include a single ESP-IDF header.** It is
pure C. This is what makes it host-testable with no hardware and no emulation,
and it is the main reason the layering exists. An agent that adds
`#include "esp_wifi.h"` to `domain/` has broken the build contract.

Services depend on driver *interfaces* (headers under
`drivers/peripherals/*/include/`), never on the implementation. This is what
lets CMock substitute a mock driver in host tests.

## 2. Directory layout

```
components/
├── domain/
│   ├── CMakeLists.txt
│   ├── types/include/
│   │   ├── ftm_measurement.h      measurement sample, quality metrics
│   │   ├── ftm_station.h          station/anchor identity + position
│   │   ├── ftm_calibration.h      calibration record, table contract
│   │   └── ftm_result.h           error/result enum used across layers
│   └── core/
│       ├── include/
│       │   ├── ftm_distance.h     rtt -> distance, calibration application
│       │   ├── ftm_filter.h       rolling median / EMA / outlier rejection
│       │   └── ftm_trilateration.h  N-anchor 3D position solve
│       └── src/
├── services/
│   ├── CMakeLists.txt
│   ├── middleware/
│   │   ├── include/
│   │   │   ├── ftm_scheduler.h    measurement loop, anchor round-robin
│   │   │   └── ftm_calib_store.h  calibration table access
│   │   └── src/
│   └── protocols/
│       ├── include/
│       │   └── ftm_csv.h          CSV sample serialisation
│       └── src/
└── drivers/
    ├── CMakeLists.txt
    ├── peripherals/
    │   └── wifi/
    │       ├── include/
    │       │   ├── wifi_ftm.h     FTM initiator/responder operations
    │       │   └── wifi_iface.h   init, mode, scan, AP config
    │       └── src/
    └── devices/
        └── README.md              why this is empty (see §5)
```

## 3. Role selection — Strategy pattern

The firmware is one codebase. Role is chosen at build time by Kconfig, but
expressed as a **runtime vtable**, not scattered `#ifdef`s.

### Contract

```c
/* domain/types/include/ftm_role.h — no ESP-IDF types here */

typedef struct ftm_role_ctx ftm_role_ctx_t;   /* opaque, role-owned */

typedef struct {
    const char *name;                              /* "initiator" | "responder" */
    ftm_result_t (*init)  (ftm_role_ctx_t *ctx);
    ftm_result_t (*start) (ftm_role_ctx_t *ctx);
    ftm_result_t (*stop)  (ftm_role_ctx_t *ctx);
    ftm_result_t (*run)   (ftm_role_ctx_t *ctx);   /* one iteration; non-blocking-ish */
} ftm_role_strategy_t;
```

### Wiring

- `services/middleware/` declares `const ftm_role_strategy_t *ftm_role_get(void);`
- Kconfig `choice` selects exactly one implementation to compile:
  - `CONFIG_FTM_ROLE_INITIATOR` → `ftm_role_initiator.c`
  - `CONFIG_FTM_ROLE_RESPONDER` → `ftm_role_responder.c`
- `CMakeLists.txt` conditionally adds the source file. The **only** `#ifdef` on
  role lives in the CMake source list and in `ftm_role_get()`.
- `main/app_main.c` is role-agnostic:

```c
const ftm_role_strategy_t *role = ftm_role_get();
role->init(ctx);
role->start(ctx);
for (;;) { role->run(ctx); }
```

### Why this shape

- **Testable:** tests inject a fake strategy and assert the lifecycle
  (`init → start → run* → stop`), including failure at each step.
- **Extensible:** a third role (e.g. a passive sniffer, or a hybrid node that is
  both anchor and initiator) is a new file, not an edit to existing logic.
- **No conditional business logic:** each role's code reads linearly.

## 4. Scaling to N anchors

The two-board setup is a fixture, not the design.

- Each anchor has a **stable identity: its BSSID.** SSID is for discovery only;
  BSSID is the calibration key. Two anchors may share an SSID.
- Anchors sit on a **single shared channel** so the initiator never channel-hops
  mid-cycle. Channel is a build/config parameter.
- The initiator holds an **anchor table** (BSSID, position x/y/z, calibration
  offset) and round-robins measurements across it.
- At ~1.5 s per session (see `HARDWARE_FINDINGS.md` §2), a full cycle over N
  anchors takes ~1.5·N seconds. With 4 anchors that is ~6 s per 3D fix. This is
  a known, accepted limitation — record it, do not silently optimise it away.
### Positioning modes — the range-only fallback

Trilateration needs **≥4 non-coplanar anchors** for an unambiguous 3D fix. With
only 2 boards today, that is not achievable on hardware, so the system has two
explicit modes:

```c
typedef enum {
    FTM_FIX_NONE,        /* no usable ranges this cycle          */
    FTM_FIX_RANGE_ONLY,  /* < 4 anchors, or degenerate geometry  */
    FTM_FIX_POSITION_3D, /* >= 4 non-coplanar anchors            */
} ftm_fix_mode_t;
```

**Rule: if fewer than 4 usable anchors are found, report `RANGE_ONLY`** — a list
of `(station_id, distance_cm)` pairs, one per anchor ranged. No position is
computed and none is guessed.

This is not a degraded error path; it is a **useful product state**. Per-station
distances are a valid reference reading, they let the visualisation exist and be
exercised long before four boards are available, and they make the system's
honesty visible: it says what it measured rather than inventing a coordinate.

Requirements:

- The mode is **explicit in the output**. A consumer must never infer it from
  whether a position field happens to be populated.
- Degenerate geometry with ≥4 anchors also yields `RANGE_ONLY`, with the
  degeneracy as the stated reason — never a bogus 3D fix.
- Dropping below 4 anchors must **not** leave a stale 3D fix visible.
- All 3D logic is nonetheless fully validated **in host simulation** (Lsim), so
  it is correct and tested before four boards ever exist.

## 5. The empty `drivers/devices/` layer

There are currently **no external devices** — Wi-Fi is an on-chip peripheral, so
it lives in `drivers/peripherals/`.

`drivers/devices/` is created empty, containing only a `README.md`, because the
layering is a **standard applied uniformly across the project**, not something
derived per-project. When an external device appears (an IMU for dead reckoning,
a display, an SD card for logging), it has an obvious home and no restructuring
is needed.

The same principle applies to `services/protocols/` — currently just CSV, but
the network protocol for multi-anchor telemetry will land beside it.

**Do not delete empty layers as "unused".**

## 6. Calibration data flow

```
Phase 2 calibrator (tkinter)
        │  operator enters true distance, tool logs for minutes
        ▼
docs or tools/calibrator/output/calibration_<date>.csv
        │  columns: station_id,bssid,ssid,x_cm,y_cm,z_cm,
        │           offset_cm,ref_distance_cm,samples,
        │           mean_raw_rtt_ns,stddev_cm,rssi_mean,timestamp
        ▼
tools/gen_calibration_table.py   (build-time codegen)
        ▼
components/domain/types/include/ftm_calibration_table.h   (generated)
        ▼
flashed into firmware
```

**Decision: generated C header, not NVS**, for now — simplest, version
controlled, and matches the requirement that calibration "be flashed on
firmware".

The access API in `services/middleware/ftm_calib_store.h` must **abstract the
source**, so swapping to an NVS-backed table later touches one file and no
callers:

```c
ftm_result_t ftm_calib_store_lookup(const uint8_t bssid[6],
                                    ftm_calibration_t *out);
size_t       ftm_calib_store_count(void);
```

The generated header is **build output committed for reproducibility**, marked
with a `/* GENERATED — do not edit by hand */` banner and the source CSV name.

## 7. Naming and style

- Prefix everything public with `ftm_` (domain/services) or the peripheral name
  (`wifi_`) for drivers.
- Return `ftm_result_t` from anything that can fail. Drivers may return
  `esp_err_t` internally but translate at the interface boundary — **`esp_err_t`
  must not appear in `domain/` or `services/` headers.**
- Out-parameters last. Never return pointers to internal static buffers (see the
  dangling-pointer defect in `HARDWARE_FINDINGS.md` §9).
- One public header per module; no umbrella headers.
