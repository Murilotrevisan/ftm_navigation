# Phase 4 — Binary Protocol, Logging & Replay

| | |
| --- | --- |
| **Status** | Not started |
| **Depends on** | Phase 3 (definitive firmware) |
| **Blocks** | Phase 5 (positioning), Phase 6 (E2E) |
| **Read first** | `docs/PROTOCOL.md` (all), `docs/PLAN.md` (all), `docs/ARCHITECTURE.md` §4, `docs/HARDWARE_FINDINGS.md` (all), `docs/WORKFLOW.md` (all) |

---

## Objective

Implement the **UBX-style binary telemetry protocol**, plus the logging and
replay tooling that it exists to enable.

Messages, per `docs/PROTOCOL.md`:

| Message | When sent |
| --- | --- |
| `NAV-STATUS` (0x01/0x01) | **Every cycle** — fix quality + anchor count |
| `NAV-RANGE` (0x01/0x02) | **Streamed, one per anchor** as each measurement completes |
| `NAV-POSITION` (0x01/0x03) | **Only when a real 3D fix exists** — so, never in this phase |
| `MON-VERSION` (0x02/0x01) | On boot |
| `CFG-ANCHOR` (0x03/0x01) | On boot, **one per configured anchor** |

This phase implements the **encoder, the decoder, and every message except
`NAV-POSITION` emission**. `NAV-POSITION` is defined and its decoder written and
tested, but the firmware does not emit it until Phase 5 puts a working solver on
target.

`CFG-ANCHOR` is what makes a streamed `NAV-RANGE` remappable: each range carries
a `station_id`, and `CFG-ANCHOR` binds that id to a BSSID, a position, and the
applied calibration offset. Written at the head of every log alongside
`MON-VERSION`, it makes a `.ftmlog` **self-describing** — replayable with no
matching calibration CSV and no matching firmware build.

## Why this phase exists separately

The protocol is the seam that lets the 3D algorithm be **developed and proven on
the host before any of it runs on target**:

```
board --> .ftmlog --> host replay --> the SAME domain code --> position
```

Get the protocol and the logs right first, and Phase 5 becomes an offline
algorithm problem with real recorded data — including real noise and real drift
(`HARDWARE_FINDINGS.md` §8) — instead of a debugging exercise on an embedded
target with a 1.5 s measurement cycle.

## Key design rules (from `docs/PROTOCOL.md`)

1. **Absence is information.** No `NAV-POSITION` means no position. **Never
   emit it with placeholder or zeroed coordinates** — zero is a valid
   coordinate, and a sentinel is exactly what the binary format exists to avoid.
2. Sync `0xF7 0x4D`, non-ASCII so frames cannot be confused with `ESP_LOG` text
   on the same UART.
3. Little-endian, fixed layout, 8-bit Fletcher checksum over
   class/ID/length/payload (identical to UBX).
4. Unknown class/ID is **skipped via `LENGTH`**, never fatal.
5. Append-only growth: new fields at the end, bump `version`, older parsers use
   `LENGTH` to read the prefix they understand.
6. Failed measurements are still transmitted, with `status != 0`. Dropouts must
   be visible.

## Deliverables

```
components/services/protocols/ftmbin/     ONE serialiser implementation
├── include/ftmbin.h         frame constants, class/ID, checksum
├── src/
│   ├── ftmbin_encode.c      ftm_snapshot_t -> frame bytes
│   └── ftmbin_serializer.c  the ftm_serializer_t vtable
└── CMakeLists.txt           self-contained; no upward dependencies

tools/proto/
├── ftm_proto.py             host decoder (construct-based)
├── ftm_log.py               .ftmlog reader/writer
├── ftm_replay.py            replay a log through host code
└── README.md

tests/host_idf/              serialiser CONTRACT suite (L1b)
tests/tools/                 decoder + replay tests (L4)
```

**`ftmbin` is one implementation of the `ftm_serializer_t` interface defined in
Phase 3d** (`docs/ARCHITECTURE.md` §4) — not a special case. Constraints that
follow from that, and are non-negotiable:

- It consumes `ftm_snapshot_t`, a **domain type**. It must not include a driver
  header, an ESP-IDF header, or know anything about Wi-Fi or FTM sessions.
- It returns bytes into a caller-supplied buffer. **No allocation, no I/O** —
  the telemetry task owns transmission.
- No `ftmbin` type appears in any interface header.
- The directory is self-contained with no upward dependencies, so it can become
  a git submodule later by moving it, with no changes to callers.

The tests written here are the **shared contract suite** (`docs/TESTING.md`
§4.8), written against `ftm_serializer_t` and never against `ftmbin` directly.
A future nanopb or CBOR serialiser must pass this same suite unmodified — that
is what makes the module swappable in fact rather than in aspiration.

## Tasks

1. **Payload structs** exactly matching `docs/PROTOCOL.md` §3. Assert sizes at
   compile time (`_Static_assert`) — `NAV-STATUS` 20, `NAV-RANGE` 32,
   `NAV-POSITION` 28, `CFG-ANCHOR` 28 bytes. A silent padding change would
   corrupt every log ever recorded.
2. **Encoder** in `services/protocols/`. Pure, no ESP-IDF types in the public
   header (`ARCHITECTURE.md` §7). Must not allocate.
3. **Telemetry emitter** wired to the measurement cycle: `MON-VERSION` and one
   `CFG-ANCHOR` per anchor at boot; one `NAV-RANGE` per anchor as it completes;
   `NAV-STATUS` closing the cycle.
4. **Host decoder** (`tools/proto/ftm_proto.py`) using `construct`. Must
   resynchronise after corruption and count rejects.
5. **`.ftmlog` capture** in the record format of `docs/PROTOCOL.md` §7: 16-byte
   file header, then `[host_unix_us u64][frame_len u16][frame verbatim]` per
   record. **The frame bytes must be untouched** — stripping the wrapper has to
   yield exactly what the device emitted, because the live-serial decoder and
   the log decoder are the same code.
6. **Replay tool** that feeds recorded `NAV-RANGE` messages into host code,
   resolving `station_id` → position from the log's own `CFG-ANCHOR` records. In
   this phase it just re-derives ranges; Phase 5 attaches the solver.
7. **Record a real log** from the two boards at the fixed 1.00 m separation
   (`HARDWARE_FINDINGS.md` §10) and commit it as a test fixture. **Record it,
   do not synthesise it.**

## Required tests

**The serialiser contract suite (`docs/TESTING.md` §4.8) is mandatory** and must
be written against the interface, not against `ftmbin`.

Then `docs/TESTING.md` §4.7, plus:

### Encoder (L1b, container)

| Case | Expected |
| --- | --- |
| Known struct → known bytes | Golden-byte test, checked against a hand-computed frame |
| Checksum | Matches UBX Fletcher-8 over class/ID/length/payload |
| Struct sizes | `_Static_assert` 20 / 32 / 28 / 28; test fails if padding changes |
| `msg_seq` present on every message | Encoded for all four types; a message without it cannot express loss |
| Output buffer too small | Refuses and reports; never overflows |
| `dist_cm` negative | Encoded as signed, round-trips (`HARDWARE_FINDINGS.md` §4) |
| Failed measurement | Emitted with `status != 0`, `valid_count = 0` |
| `NAV-POSITION` with `fix_quality < 2` | **Encoder refuses.** Must be impossible to emit a position that should not exist |

### Decoder (L4, host venv)

| Case | Expected |
| --- | --- |
| Round-trip vs. encoder golden bytes | Exact |
| Bad checksum | Rejected **and counted**, not silently dropped |
| Truncated frame at every offset | No crash, no partial parse |
| Garbage between frames | Resynchronises on `0xF7 0x4D` |
| Sync bytes appearing inside a payload | Not a false frame start — length + checksum must disambiguate |
| Unknown class/ID | Skipped via `LENGTH`, stream continues |
| Longer payload than this version knows | Prefix parsed, remainder ignored (append-only rule) |
| `LENGTH` absurdly large | Rejected, does not allocate |
| Zero-length payload | Handled |
| Empty / truncated `.ftmlog` | Clean error, no crash |
| Log with no `NAV-POSITION` at all | Normal — must not be reported as an error |
| Interleaved `ESP_LOG` text in the stream | Skipped without losing following frames |

### `.ftmlog` and anchor remapping (L4, host venv)

| Case | Expected |
| --- | --- |
| Wrapper stripped | Yields **byte-identical** frames to the live serial stream |
| Record truncated mid-frame (log cut off) | Clean EOF, earlier records still usable |
| `frame_len` disagrees with the frame's own `LENGTH` | Rejected and counted |
| `host_unix_us` non-monotonic | Tolerated and flagged, not fatal — clock adjustments happen |
| Large `host_unix_us` gap | Surfaced as a serial-stall indicator |
| `NAV-RANGE` with a `station_id` having no `CFG-ANCHOR` | Explicit "unknown anchor" — **never** silently assumed to be station 0 |
| `CFG-ANCHOR` with `flags` bit0 clear | Position treated as **unknown**, never as `0,0,0` |
| Duplicate `station_id` in `CFG-ANCHOR` records | Rejected |
| Same BSSID under two different `station_id`s | Detected and reported |
| `CFG-ANCHOR` records absent entirely | Ranges still decode; positions explicitly unavailable |
| Log replayed against a different firmware build | Works — log is self-describing |

## E2E test (L3, autonomous, host venv)

`tests/e2e/test_protocol.py`:
- Flash the definitive firmware to both boards (1.00 m apart).
- Capture a `.ftmlog` for ≥ 60 measurement cycles.
- Assert: every cycle has exactly one `NAV-STATUS`; `num_ranges_sent` matches
  the `NAV-RANGE` count; **zero `NAV-POSITION` messages**; checksum reject count
  is zero; `fix_quality == 1` and `num_anchors == 1` throughout.
- Assert distances land in the standing band (mean over ≥60 samples, 1.00 m
  ±0.75 m, valid ratio ≥ 0.8).

## Acceptance criteria

- [ ] `ftmbin` implements `ftm_serializer_t` and **passes the shared contract
      suite** (`docs/TESTING.md` §4.8) written against the interface.
- [ ] `ftmbin` includes no driver header, no ESP-IDF header; allocates nothing;
      performs no I/O.
- [ ] No `ftmbin` type appears in any interface header.
- [ ] `components/services/protocols/ftmbin/` is self-contained — submodule-ready
      without restructuring.
- [ ] All five messages implemented per `docs/PROTOCOL.md`, sizes statically
      asserted (20 / 32 / 28 / 28).
- [ ] `msg_seq` on every message, assigned at enqueue; `dropped_total` in
      `NAV-STATUS`. Decoder detects gaps and reports them without gating
      navigation.
- [ ] Firmware emits `MON-VERSION` + `CFG-ANCHOR` at boot, `NAV-RANGE` streamed
      per anchor, `NAV-STATUS` per cycle; **never** `NAV-POSITION`.
- [ ] Encoder structurally cannot emit `NAV-POSITION` when `fix_quality < 2`.
- [ ] Host decoder resynchronises, rejects-and-counts bad checksums, skips
      unknown messages.
- [ ] `.ftmlog` records carry `host_unix_us`; **stripping the wrapper yields
      byte-identical frames**, verified by test.
- [ ] `station_id` → position resolution works from the log's own `CFG-ANCHOR`
      records, with unknown ids reported explicitly.
- [ ] A **real recorded** `.ftmlog` committed as a fixture.
- [ ] Replay tool reads it and reproduces the ranges.
- [ ] Every worst case above tested.
- [ ] Work on a `phase-4/...` branch; full test output reported
      (`docs/WORKFLOW.md`).

## Design rationale

- **`NAV-RANGE` is streamed per anchor**, not batched per cycle — lower latency,
  simpler buffering. Each message carries `station_id` so it stands alone.
- **`.ftmlog` carries a host timestamp** in a record wrapper around the frame,
  not inside the messages. The frame stays byte-exact, so the live-serial and
  log decoders remain one piece of tested code, while host wall-clock time is
  available for correlating across boards and against operator actions.
- **`CFG-ANCHOR` exists** so `station_id` maps to a position without an external
  file, making every log self-describing.
