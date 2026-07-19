# Telemetry Protocol — Binary (UBX-style)

Modelled on the **u-blox UBX binary protocol**, not NMEA. Fixed-layout binary
frames with a class/ID header and a Fletcher checksum.

---

## 1. Why binary, and why message presence carries meaning

A text protocol has to encode "there is no position" *inside* a position field —
empty commas, sentinel values, `0,0,0`. Every consumer then has to special-case
it, and a parser bug turns "no fix" into a coordinate at the origin.

**In this protocol a message that has no meaningful content is simply not
sent.** No `NAV-POSITION` message means there is no position. There is nothing
to parse, nothing to misinterpret, and no sentinel to get wrong.

Design rules:

1. **Fixed-layout binary.** No delimiter scanning, no float parsing, no locale
   hazards. Payload structs are `memcpy`-able.
2. **Absence is information.** `NAV-POSITION` is emitted **only** when a real 3D
   fix exists. Never emit it with placeholder coordinates.
3. **Status always travels with data.** `NAV-STATUS` closes every cycle,
   carrying fix quality and anchor count.
4. **Little-endian throughout**, matching the ESP32-C3 (RISC-V LE) so the
   firmware side is a straight struct copy.
5. **Versioned and length-prefixed**, so a consumer can skip a message class it
   does not know and resynchronise cleanly.
6. **Append-only growth.** New fields go at the end of a payload and bump
   `version`; older parsers read the prefix they understand using `length`.

## 2. Frame

```
+--------+--------+-------+------+----------+---------+--------+--------+
| SYNC1  | SYNC2  | CLASS |  ID  |  LENGTH  | PAYLOAD |  CK_A  |  CK_B  |
| 0xF7   | 0x4D   |  u8   |  u8  | u16 LE   | LENGTH  |  u8    |  u8    |
+--------+--------+-------+------+----------+---------+--------+--------+
```

- **Sync**: `0xF7 0x4D`. Deliberately non-ASCII so frames cannot be confused
  with `ESP_LOG` text on the same UART.
- **LENGTH**: payload bytes only, excluding header and checksum.
- **Checksum**: 8-bit Fletcher over `CLASS`, `ID`, `LENGTH`, `PAYLOAD` —
  identical to UBX:

```c
ck_a = 0; ck_b = 0;
for (each byte b in [CLASS, ID, LENGTH_LO, LENGTH_HI, PAYLOAD...]) {
    ck_a = (uint8_t)(ck_a + b);
    ck_b = (uint8_t)(ck_b + ck_a);
}
```

Overhead is 8 bytes per message.

## 3. Message catalogue

| Class | ID | Name | When sent |
| --- | --- | --- | --- |
| `0x01` | `0x01` | `NAV-STATUS` | **Every cycle**, always |
| `0x01` | `0x02` | `NAV-RANGE` | Once per anchor measured (streamed) |
| `0x01` | `0x03` | `NAV-POSITION` | **Only** when a 3D fix exists |
| `0x02` | `0x01` | `MON-VERSION` | On boot, and on request |
| `0x03` | `0x01` | `CFG-ANCHOR` | On boot, **one per configured anchor** |

Class `0x02` (MON) is diagnostics; `0x03` (CFG) is configuration. Unknown
classes must be skipped via `LENGTH`, not treated as an error.

### 3.0 `msg_seq` — present on every message

Every message carries a **monotonic `msg_seq`**, assigned by the telemetry layer
at the moment the message is enqueued.

Its only purpose is **loss detection**. The device drops the oldest queued
message under backpressure rather than blocking (`docs/RTOS.md` §5), because a
navigation consumer needs current data, not a backlog of stale data. A gap in
`msg_seq` is how the consumer learns that happened.

**`msg_seq` is diagnostic. It is never an input to navigation** — a consumer
must not attempt to reconstruct, interpolate or wait for missing messages. It
navigates on what arrived.

### 3.1 `NAV-STATUS` (0x01 0x01) — 20 bytes

Closes every measurement cycle. This is the message that tells a consumer how
much to trust everything else in the cycle.

| Offset | Type | Field | Notes |
| --- | --- | --- | --- |
| 0 | `u8` | `version` | Currently `1` |
| 1 | `u8` | `fix_quality` | See §4 |
| 2 | `u8` | `num_anchors` | Anchors with a **usable** range this cycle |
| 3 | `u8` | `num_ranges_sent` | `NAV-RANGE` count in this cycle |
| 4 | `u32` | `msg_seq` | See §3.0 |
| 8 | `u32` | `cycle_seq` | Monotonic cycle counter |
| 12 | `u32` | `uptime_ms` | Device uptime |
| 16 | `u32` | `dropped_total` | Running total of messages dropped at the queue |

`dropped_total` exists for a consumer that joined the stream mid-way and has no
earlier `msg_seq` to compare against. Together the two give both a precise local
gap and a durable running total.

### 3.2 `NAV-RANGE` (0x01 0x02) — 32 bytes

**Streamed: one message per anchor, emitted as soon as that measurement
completes** (~1.5 s apart, see `HARDWARE_FINDINGS.md` §2). Keeps latency low and
buffering trivial.

Because messages are streamed rather than batched, **each one must identify its
anchor on its own**. It carries two identifiers:

- **`station_id`** — the index the host uses to look up the anchor's position
  (see `CFG-ANCHOR`, §3.5). This is the field that makes ranges remappable to
  coordinates.
- **`bssid`** — the stable physical identity, so a log stays interpretable even
  if station indices are renumbered between builds.

Both are present deliberately: `station_id` is the fast lookup key,
`bssid` is the ground truth that survives reconfiguration.

| Offset | Type | Field | Notes |
| --- | --- | --- | --- |
| 0 | `u8` | `version` | Currently `1` |
| 1 | `u8` | `station_id` | Index into the calibration table |
| 2 | `u8` | `valid_count` | Valid FTM readings |
| 3 | `u8` | `total_count` | Total readings received |
| 4 | `u8[6]` | `bssid` | Stable anchor identity |
| 10 | `i8` | `rssi_dbm` | Mean RSSI |
| 11 | `u8` | `status` | 0 = OK, non-zero = FTM failure code |
| 12 | `i32` | `dist_cm` | Calibrated distance. **Signed** — `HARDWARE_FINDINGS.md` §4 |
| 16 | `f32` | `rtt_raw_ns` | Sub-ns precision. **Calibrate against this**, not `dist_cm` (§3) |
| 20 | `u32` | `msg_seq` | See §3.0 |
| 24 | `u32` | `cycle_seq` | Correlates to `NAV-STATUS` |
| 28 | `u32` | `uptime_ms` | Device uptime |

**A failed measurement is still sent**, with `status != 0` and
`valid_count = 0`. Dropouts must be visible. `dist_cm` and `rtt_raw_ns` are
meaningless when `status != 0` and must be ignored — the consumer keys off
`status`, not off a sentinel value.

### 3.3 `NAV-POSITION` (0x01 0x03) — 28 bytes

**Emitted only when a genuine 3D fix exists** (`fix_quality >= 2`). Its absence
is how "no position" is communicated.

| Offset | Type | Field | Notes |
| --- | --- | --- | --- |
| 0 | `u8` | `version` | Currently `1` |
| 1 | `u8` | `fix_quality` | Repeated so the message is self-contained |
| 2 | `u8` | `num_anchors` | Anchors used in the solve |
| 3 | `u8` | `reserved` | Zero |
| 4 | `i32` | `x_cm` | |
| 8 | `i32` | `y_cm` | |
| 12 | `i32` | `z_cm` | |
| 16 | `u32` | `residual_cm` | Solve residual — the only signal the fix is inconsistent |
| 20 | `u32` | `msg_seq` | See §3.0 |
| 24 | `u32` | `cycle_seq` | |

### 3.4 `MON-VERSION` (0x02 0x01)

Firmware version, protocol version, role, build ID. Sent on boot so a log file
is self-describing when replayed later.

### 3.5 `CFG-ANCHOR` (0x03 0x01) — 28 bytes

**One per configured anchor, emitted at boot.** This is what lets the host map a
streamed `NAV-RANGE` back to a position.

| Offset | Type | Field | Notes |
| --- | --- | --- | --- |
| 0 | `u8` | `version` | Currently `1` |
| 1 | `u8` | `station_id` | The key `NAV-RANGE.station_id` refers to |
| 2 | `u8[6]` | `bssid` | Physical identity |
| 8 | `u8` | `flags` | bit0 = position known; bit1 = calibrated |
| 9 | `u8` | `reserved` | Zero |
| 10 | `i16` | `offset_cm` | Applied T1 calibration offset (`int16_t`, per the ESP API) |
| 12 | `i32` | `x_cm` | Valid only if `flags` bit0 |
| 16 | `i32` | `y_cm` | |
| 20 | `i32` | `z_cm` | |
| 24 | `u32` | `msg_seq` | See §3.0 |

**Why this exists.** Without it, a `.ftmlog` is only interpretable alongside the
exact calibration CSV that produced the firmware — and that coupling breaks the
moment either changes. With it, **a log is fully self-describing**: anchor
identity, position and applied calibration all travel with the data. A log
recorded today can be replayed in a year, against a different build, and still
solve correctly.

That property is what makes the Phase 5 host-first workflow trustworthy, so
`CFG-ANCHOR` is not optional decoration.

`flags` bit0 exists because with 2 boards the anchor positions are not yet
surveyed. An anchor with an unknown position is honestly marked as such rather
than defaulting to `0,0,0` — consistent with §1 rule 2.

## 4. Fix quality

| Value | Name | `NAV-POSITION` sent? |
| --- | --- | --- |
| `0` | `NO_FIX` — no usable ranges | No |
| `1` | `RANGE_ONLY` — 1–3 anchors, distances valid | No |
| `2` | `POSITION_3D` — ≥4 non-coplanar anchors | Yes |
| `3` | `POSITION_3D_DEGRADED` — ≥4 anchors, poor geometry or high residual | Yes, but do not trust it |

**With the current 2 boards every cycle is `fix_quality = 1`,
`num_anchors = 1`, and no `NAV-POSITION` is ever emitted.** That is correct
behaviour, not a gap.

## 5. Example — today's 2-board setup

At boot, one `CFG-ANCHOR` per configured anchor. The position is not yet
surveyed, so `flags` bit0 is clear and the coordinates are explicitly **not**
claimed:

```
CFG-ANCHOR   class 0x03  id 0x01  LENGTH 28 (0x1C)
  version=1  station_id=0  bssid=14:63:93:8d:98:75
  flags=0x02 (calibrated, position UNKNOWN)   offset_cm=0
  x/y/z = not valid, flags bit0 clear         msg_seq=0
```

Then, per measurement cycle:

```
NAV-RANGE    class 0x01  id 0x02  LENGTH 32 (0x20)
  version=1  station_id=0  valid=30/30  bssid=14:63:93:8d:98:75
  rssi=-52   status=0     dist_cm=118   rtt_raw_ns=8.489
  msg_seq=87 cycle_seq=22 uptime_ms=132004

NAV-STATUS   class 0x01  id 0x01  LENGTH 20 (0x14)
  version=1  fix_quality=1 (RANGE_ONLY)  num_anchors=1  num_ranges_sent=1
  msg_seq=88 cycle_seq=22 uptime_ms=132004  dropped_total=0
```

No `NAV-POSITION` is emitted. The consumer maps `station_id=0` to its anchor via
`CFG-ANCHOR`, renders the per-station distance readout, and has nothing to
mistake for a coordinate.

> Byte-exact golden vectors are **generated and checked by the Phase 4 test
> suite**, not written by hand here. Hand-transcribed hex in documentation drifts
> from the implementation and is then trusted anyway; the encoder tests are the
> authority on exact bytes.

## 6. Consumer requirements

- **Switch behaviour on `fix_quality` from `NAV-STATUS`.** Never infer state
  from whether a message happened to arrive with plausible numbers.
- **Clear any retained position** when a cycle reports `fix_quality < 2`. A
  stale coordinate is worse than none.
- **Navigate on the latest data only.** The device drops the oldest queued
  message under backpressure (`docs/RTOS.md` §5) precisely so the freshest
  reading reaches you. Do not buffer, re-order or wait for a missing `msg_seq`.
- **Track `msg_seq` gaps and `dropped_total` for diagnosis**, and surface them —
  but never let them gate navigation. A gap means data was lost, not that the
  current reading is suspect.
- **Reject and count** frames with a bad checksum. A rising reject count is the
  symptom of a serial problem; silently dropping hides it.
- **Resynchronise** on `SYNC1 SYNC2` after any framing error.
- **Skip unknown class/ID** using `LENGTH`; do not treat it as fatal.
- Treat `valid_count / total_count < 0.8` as a bad range even when
  `status == 0` — a clamped session reports success with a collapsed valid count
  (`HARDWARE_FINDINGS.md` §6).

## 7. `.ftmlog` — logging and replay

This is the point of everything above.

### File layout

```
File header (16 bytes, once)
+------------+---------+-------+-----------+
| "FTMLOG\0" | version | flags | reserved  |
|  8 bytes   |   u8    |  u8   |  6 bytes  |
+------------+---------+-------+-----------+

Then a sequence of records:
+---------------+-----------+----------------------+
| host_unix_us  | frame_len |  frame (verbatim)    |
|    u64 LE     |  u16 LE   |   frame_len bytes    |
+---------------+-----------+----------------------+
```

- **`host_unix_us`** — host wall-clock time in microseconds since the Unix
  epoch, recorded when the frame was read from the serial port.
- **`frame`** — the complete on-wire frame **byte-for-byte**, sync bytes and
  checksum included. Nothing reinterpreted, reordered or normalised.

### Why the timestamp wraps the frame instead of going inside the messages

The device has no wall clock. Messages carry `uptime_ms`, which is
device-relative and resets on reboot — enough to order events within one run,
useless for correlating across boards or against an operator's actions.

Wrapping keeps both properties:

- **The frame stays pristine.** Strip the wrapper and you have exactly what the
  device emitted — so the decoder used on a live serial port and the decoder
  used on a log file are **the same code, tested once**.
- **Host time is available** for diagnosing serial stalls, correlating the
  Phase 6 movement test against operator prompts, and aligning logs captured
  from several boards.

Use `uptime_ms` for device-side ordering and `host_unix_us` for anything
involving the outside world. The two will drift apart; that drift is itself
diagnostic.

### Replay

```
board --> .ftmlog --> host replay --> the SAME domain code --> position
```

The replay tool feeds recorded `NAV-RANGE` messages into the identical
`domain/core` trilateration the firmware uses, resolving each `station_id` to a
position from the `CFG-ANCHOR` records at the head of the log. The algorithm is
proven against real recorded measurements — with their real noise and drift —
and only then compiled for the target, where it begins emitting `NAV-POSITION`.

Because `MON-VERSION` and `CFG-ANCHOR` are written at the head of every log,
**a log needs no external file to be interpreted** — no matching calibration
CSV, no matching firmware build. A log recorded today replays correctly in a
year against a different build.
