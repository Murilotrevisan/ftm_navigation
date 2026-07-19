# Telemetry Protocol

Modelled on NMEA 0183 / u-blox practice: **fix status travels with the data**,
so a consumer always knows how much to trust what it just received, without
inferring it from which fields happen to be populated.

The wire format today is **CSV over serial**. The sentence structure below is
the stable contract; a binary/own protocol may replace the encoding later
without changing the semantics.

---

## 1. Design rules

1. **Every cycle reports its fix quality and anchor count**, exactly as NMEA
   `GGA` carries fix quality and satellite count. A consumer must never have to
   guess.
2. **Two sentence types**, mirroring NMEA's per-satellite (`GSV`) vs. per-fix
   (`GGA`) split:
   - `$FTMRNG` — one per anchor ranged. The raw measurement.
   - `$FTMFIX` — one per measurement cycle. The derived state.
3. **Failed measurements are still transmitted**, with a non-zero status and
   empty measurement fields. Dropouts must be visible, not absent.
4. **Checksummed.** Serial corruption is real and silent; an NMEA-style XOR
   checksum is nearly free and catches it.
5. **Append-only evolution.** New fields go at the end, before the checksum. A
   parser must ignore trailing fields it does not recognise rather than fail.

## 2. Sentences

### `$FTMRNG` — one range measurement to one anchor

```
$FTMRNG,<seq>,<uptime_ms>,<station_id>,<bssid>,<dist_cm>,<rtt_raw_ns>,<rssi_dbm>,<valid>,<total>,<status>*<cs>
```

| Field | Type | Notes |
| --- | --- | --- |
| `seq` | uint32 | Monotonic measurement counter |
| `uptime_ms` | uint32 | Device uptime at report |
| `station_id` | uint8 | Anchor index in the calibration table |
| `bssid` | hex | `aabbccddeeff`, the stable anchor identity |
| `dist_cm` | **int32** | Calibrated distance. **Signed** — see `HARDWARE_FINDINGS.md` §4 |
| `rtt_raw_ns` | float | Sub-nanosecond precision. **Calibrate against this**, not `dist_cm` (§3) |
| `rssi_dbm` | int8 | Mean RSSI over the session |
| `valid` | uint8 | Valid readings in the session |
| `total` | uint8 | Total readings received |
| `status` | uint8 | 0 = OK, non-zero = FTM failure code |

Empty measurement fields on failure, e.g.:
`$FTMRNG,412,88231,0,1463938d9875,,,,0,30,3*7A`

### `$FTMFIX` — the derived state for one cycle

```
$FTMFIX,<seq>,<uptime_ms>,<fix_quality>,<num_anchors>,<x_cm>,<y_cm>,<z_cm>,<residual_cm>*<cs>
```

| Field | Type | Notes |
| --- | --- | --- |
| `seq` | uint32 | Cycle counter |
| `uptime_ms` | uint32 | Device uptime |
| `fix_quality` | uint8 | See §3 |
| `num_anchors` | uint8 | Anchors with a **usable** range this cycle |
| `x_cm`,`y_cm`,`z_cm` | int32 | **Empty unless `fix_quality >= 2`** |
| `residual_cm` | uint32 | Solve residual; empty when no position |

## 3. Fix quality

| Value | Name | Meaning |
| --- | --- | --- |
| `0` | `NO_FIX` | No usable ranges this cycle |
| `1` | `RANGE_ONLY` | 1–3 anchors. Distances valid, **no position computed** |
| `2` | `POSITION_3D` | ≥4 non-coplanar anchors, position valid |
| `3` | `POSITION_3D_DEGRADED` | ≥4 anchors but poor geometry or high residual — position present, **do not trust it** |

Maps directly onto `ftm_fix_mode_t` (`docs/ARCHITECTURE.md` §4), with `3`
splitting out the degraded case that `POSITION_3D` would otherwise hide.

**With the current 2 boards, every cycle reports `fix_quality=1`,
`num_anchors=1`.** That is correct and expected, not a defect.

## 4. Checksum

NMEA-style: XOR of every character **between** `$` and `*`, exclusive, as two
uppercase hex digits.

```
$FTMFIX,17,42311,1,1,,,,*4C
```

Consumers must **reject** a sentence whose checksum does not match, and count
the rejection rather than silently dropping it — a rising reject count is the
symptom of a serial problem.

## 5. Example — a cycle with the current 2-board setup

```
$FTMRNG,88,132004,0,1463938d9875,118,8.489,-52,30,30,0*15
$FTMFIX,22,132004,1,1,,,,*4C
```

`fix_quality=1` (range only), `num_anchors=1`, position fields empty. The host
visualisation renders the per-station distance readout and **must not** display
a position.

## 6. Example — a future 4-anchor cycle

```
$FTMRNG,301,540112,0,1463938d9875,118,8.49,-52,30,30,0*1D
$FTMRNG,302,541620,1,1463938d1122,342,22.81,-61,29,30,0*2E
$FTMRNG,303,543140,2,1463938d3344,507,33.82,-64,28,30,0*3B
$FTMRNG,304,544655,3,1463938d5566,289,19.27,-58,30,30,0*49
$FTMFIX,76,544655,2,4,120,240,95,14*6D
```

## 7. Host consumer requirements

- **Switch visualisation on `fix_quality`**, never on whether `x_cm` is
  populated. This is the whole point of carrying status with data.
- Never retain a stale position after a cycle reports `fix_quality < 2`.
- Treat `valid/total < 0.8` as a bad range even when `status = 0` — a clamped
  session reports success with a collapsed valid count
  (`HARDWARE_FINDINGS.md` §6).
- Tolerate unknown trailing fields (rule 5).

## 8. Future

The CSV encoding is a stage, not the destination. When bandwidth or parse cost
matters, replace the encoding with a binary framing while keeping the sentence
semantics, field order, and `fix_quality` meanings identical — so host code
changes only its decoder.
