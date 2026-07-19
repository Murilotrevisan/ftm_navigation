# Architecture

Applies to the definitive firmware (Phase 3 onward). Phases 1 and 2 produce
tools under `tools/` and are exempt.

Concurrency design is in `docs/RTOS.md`. Wire format is in `docs/PROTOCOL.md`.

---

## 1. Layers

Three layers, strictly ordered. **Dependencies point downward only.**

```
┌─────────────────────────────────────────────────────┐
│  main/                 entry point, role selection  │
├─────────────────────────────────────────────────────┤
│  services/                                          │
│    middleware/   orchestration, scheduling, tasks   │
│    protocols/    serialisers (swappable)            │
├─────────────────────────────────────────────────────┤
│  domain/                                            │
│    types/        data structures, contracts         │
│    core/         pure logic: math, filters, models  │
├─────────────────────────────────────────────────────┤
│  drivers/                                           │
│    peripherals/  wifi (on-chip peripherals)         │
│    devices/      (empty — see §7)                   │
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
pure C. That is what makes it host-testable with no hardware and no emulation,
and it is the main reason the layering exists. An agent that adds
`#include "esp_wifi.h"` to `domain/` has broken the build contract.

Services depend on driver *interfaces* (headers under
`drivers/peripherals/*/include/`), never on implementations. This is what lets
CMock substitute a mock driver in host tests.

## 2. Swappable modules — the general contract

Several modules must be replaceable without disturbing the rest of the system:
the **role** (initiator/responder), the **serialiser** (binary now, protobuf
later), and eventually the **transport**.

All of them follow one pattern, so there is a single idea to learn:

1. **An interface header** declaring a `const` vtable struct, living in the
   layer that *consumes* the module — never in the implementation's directory.
2. **Implementations in sibling directories**, each self-contained with its own
   `CMakeLists.txt` and no upward dependencies.
3. **Kconfig `choice` selects exactly one.** CMake conditionally adds only that
   implementation's sources. The only `#ifdef` lives in the CMake source list
   and in the one accessor function.
4. **Only domain types cross the interface.** No implementation-specific type
   ever appears in the interface header.
5. **A shared contract test suite** that *every* implementation must pass.

Point 5 is the one that actually delivers the guarantee. An interface alone does
not prove a replacement behaves correctly — a contract suite does. Swapping in a
new serialiser means running the same tests against it; if they pass, nothing
upstream can tell the difference. Without that suite, "swappable" is an
aspiration.

Because each implementation directory is self-contained with no upward
dependencies, **any of them can become a git submodule later** by moving the
directory and adding it as a submodule — no restructuring, no changes to
callers.

## 3. Directory layout

```
components/
├── domain/
│   ├── types/include/
│   │   ├── ftm_result.h            shared result/error vocabulary
│   │   ├── ftm_measurement.h       one FTM sample + quality metrics
│   │   ├── ftm_station.h           anchor identity + position
│   │   ├── ftm_calibration.h       calibration record
│   │   ├── ftm_fix.h               fix mode / quality
│   │   ├── ftm_snapshot.h          queue payload (docs/RTOS.md §4)
│   │   └── ftm_role.h              role vtable
│   └── core/
│       ├── include/
│       │   ├── ftm_distance.h      rtt -> distance, calibration
│       │   ├── ftm_filter.h        rolling median / outlier rejection
│       │   └── ftm_trilateration.h N-anchor 3D solve
│       └── src/
├── services/
│   ├── middleware/
│   │   ├── include/
│   │   │   ├── ftm_scheduler.h     measurement loop, anchor round-robin
│   │   │   ├── ftm_calib_store.h   calibration table access
│   │   │   ├── ftm_telemetry.h     tx task, queue, drop counter
│   │   │   └── ftm_serializer.h    SERIALISER INTERFACE (§4)
│   │   └── src/
│   │       ├── ftm_role.c
│   │       ├── ftm_role_initiator.c   iff CONFIG_FTM_ROLE_INITIATOR
│   │       └── ftm_role_responder.c   iff CONFIG_FTM_ROLE_RESPONDER
│   └── protocols/
│       ├── ftmbin/                 iff CONFIG_FTM_SERIALIZER_FTMBIN
│       │   ├── include/ftmbin.h
│       │   ├── src/
│       │   └── CMakeLists.txt
│       └── nanopb/                 future, same contract
└── drivers/
    ├── peripherals/wifi/
    │   ├── include/
    │   │   ├── wifi_iface.h        init, mode, scan, AP config
    │   │   └── wifi_ftm.h          FTM initiator/responder operations
    │   ├── src/
    │   └── test_apps/
    └── devices/
        └── README.md               why this is empty (§7)
```

## 4. Serialisation is a separate, swappable module

Serialisation **consumes a domain snapshot and produces bytes**. Nothing else.

```c
/* services/middleware/include/ftm_serializer.h */

typedef struct {
    const char *name;               /* "ftmbin", "nanopb", ... */

    /* Encode one snapshot. Returns bytes written, or 0 on failure.
     * Must never allocate and never write past `cap`. */
    size_t (*encode)(const ftm_snapshot_t *in, uint8_t *out, size_t cap);

    /* Upper bound on encode() output, for static buffer sizing. */
    size_t (*max_encoded_size)(void);
} ftm_serializer_t;

const ftm_serializer_t *ftm_serializer_get(void);
```

### The boundaries that make it swappable

- **Input is `ftm_snapshot_t`, a domain type** (`docs/RTOS.md` §4). The
  serialiser **must not** include any driver header, any ESP-IDF header, or know
  anything about Wi-Fi, FTM sessions or peripherals. It translates a struct into
  bytes.
- **Output is bytes into a caller-supplied buffer.** No allocation, no I/O. The
  serialiser does not know what a UART is; the telemetry task owns transmission.
- **No serialiser type escapes the interface.** `ftm_proto_frame_t` and friends
  stay inside `protocols/ftmbin/`.

That gives a clean three-stage chain with three independent swap points:

```
peripheral ──> domain snapshot ──> serialiser ──> transport
  (driver)      (queue, RTOS)        (bytes)       (UART)
```

Replacing the binary format with nanopb changes exactly one directory. Changing
the transport to Wi-Fi or BLE changes exactly one file. Neither touches the
measurement path.

### Contract test suite

Every serialiser implementation must pass one shared suite
(`docs/TESTING.md` §4.8), covering at minimum: round-trip fidelity for every
snapshot kind, `cap` too small handled without overflow, `max_encoded_size()`
actually bounding real output, and the invariant that a position snapshot with
`fix_quality < 2` is refused.

**A serialiser that has not passed the contract suite is not a valid
implementation** — this is what makes swapping safe rather than hopeful.

### Why the wire format is not the deliverable

`docs/PROTOCOL.md` specifies `ftmbin`, the **first** serialiser. It is one
implementation of this interface, not the architecture. Treating the protocol
spec as swappable from the start is what keeps the option of protobuf, CBOR, or
a vendor format open without a rewrite.

## 5. Role selection

The same swappable-module pattern (§2), applied to initiator vs. responder.

```c
/* domain/types/include/ftm_role.h — no ESP-IDF types */

typedef struct ftm_role_ctx ftm_role_ctx_t;   /* opaque, role-owned */

typedef struct {
    const char *name;                              /* "initiator" | "responder" */
    ftm_result_t (*init)  (ftm_role_ctx_t *ctx);
    ftm_result_t (*start) (ftm_role_ctx_t *ctx);
    ftm_result_t (*stop)  (ftm_role_ctx_t *ctx);
    ftm_result_t (*run)   (ftm_role_ctx_t *ctx);   /* one iteration */
} ftm_role_strategy_t;
```

`main/app_main.c` is role-agnostic:

```c
const ftm_role_strategy_t *role = ftm_role_get();
role->init(ctx);
role->start(ctx);
for (;;) { role->run(ctx); }
```

Tests inject a fake strategy and assert the lifecycle
(`init → start → run* → stop`), including failure injected at each step. A third
role — a passive sniffer, or a node that is both anchor and initiator — is a new
file, not an edit to existing logic.

## 6. Scaling to N anchors

Two boards is the current test fixture, not the architecture.

- Each anchor's stable identity is its **BSSID**. SSID is for discovery only.
- Anchors sit on a **single shared channel** so the initiator never channel-hops
  mid-cycle.
- The initiator holds an **anchor table** (BSSID, position, calibration offset)
  and round-robins across it.
- At ~1.5 s per session (`HARDWARE_FINDINGS.md` §2), a full cycle over N anchors
  takes ~1.5·N seconds — ~6 s per 3D fix with 4 anchors. A known, accepted
  limitation.

### Positioning modes

```c
typedef enum {
    FTM_FIX_NONE,        /* no usable ranges this cycle          */
    FTM_FIX_RANGE_ONLY,  /* < 4 anchors, or degenerate geometry  */
    FTM_FIX_POSITION_3D, /* >= 4 non-coplanar anchors            */
} ftm_fix_mode_t;
```

**Fewer than 4 usable anchors reports `RANGE_ONLY`** — a list of
`(station_id, distance_cm)` pairs. No position is computed and none is guessed.

`RANGE_ONLY` is a useful product state, not an error path: per-station distances
are a valid reference reading, they let the visualisation be exercised long
before four boards exist, and they keep the system honest — it reports what it
measured rather than inventing a coordinate.

- The mode is transmitted explicitly as `fix_quality` with `num_anchors` every
  cycle (`docs/PROTOCOL.md`).
- **Absence carries meaning:** with no 3D fix, no position message is emitted at
  all. There is no placeholder coordinate to misparse.
- Degenerate geometry with ≥4 anchors also yields `RANGE_ONLY`, with the
  degeneracy stated — never a bogus 3D fix.
- Dropping below 4 anchors must not leave a stale 3D fix visible.
- 3D logic is fully validated in host simulation and log replay, so it is
  correct and tested before four boards exist.

## 7. The empty `drivers/devices/` layer

There are currently no external devices — Wi-Fi is on-chip, so it lives in
`drivers/peripherals/`.

`drivers/devices/` exists, empty but for a `README.md`, because the layering is
a **standard applied uniformly**, not something re-derived per project. When an
external device appears (an IMU for dead reckoning, a display, an SD card), it
has an obvious home and nothing needs restructuring.

**Do not delete empty layers as "unused".**

## 8. Calibration data flow

```
Phase 2 calibrator (operator enters true distance, logs for minutes)
        ▼
tools/calibrator/output/calibration_<date>.csv
        │  station_id,bssid,ssid,x_cm,y_cm,z_cm,offset_cm,
        │  ref_distance_cm,samples,mean_raw_rtt_ns,stddev_cm,rssi_mean,timestamp
        ▼
tools/gen_calibration_table.py   (build-time codegen)
        ▼
components/domain/types/include/ftm_calibration_table.h   (generated)
        ▼
flashed into firmware, and broadcast at boot as CFG-ANCHOR
```

The calibration table is a **generated C header**, committed for
reproducibility, banner-marked `/* GENERATED — do not edit by hand */` with its
source CSV named.

Access is abstracted so an NVS-backed table can replace it without touching
callers:

```c
ftm_result_t ftm_calib_store_lookup(const uint8_t bssid[6], ftm_calibration_t *out);
size_t       ftm_calib_store_count(void);
```

## 9. Naming and style

- Prefix public symbols with `ftm_` (domain/services) or the peripheral name
  (`wifi_`) for drivers.
- Return `ftm_result_t` from anything that can fail. Drivers may use `esp_err_t`
  internally but translate at the boundary — **`esp_err_t` must not appear in
  any `domain/` or `services/` public header.**
- Out-parameters last. Never return pointers to internal static buffers
  (`HARDWARE_FINDINGS.md` §9 records where the upstream example does).
- One public header per module; no umbrella headers.
