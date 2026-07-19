# Hardware Findings — Verified Measurements

> **Normative.** These are measured facts from real hardware, not estimates. Do
> not re-derive them. If a new measurement contradicts something here, update
> this file and flag the change explicitly.
>
> Measured with the stock Espressif FTM console example on ESP-IDF v5.5.2,
> ESP32-C3 on COM3 (responder) and COM4 (initiator).

---

## 1. Platform facts

| Fact | Value |
| --- | --- |
| `SOC_WIFI_FTM_SUPPORT` on ESP32-C3 | `y` — both initiator and responder |
| `CONFIG_ESP_WIFI_FTM_ENABLE` | **`n` by default — must be set explicitly** |
| `CONFIG_ESP_WIFI_FTM_INITIATOR_SUPPORT` | `y` by default, **but depends on `ESP_WIFI_FTM_ENABLE`** |
| `CONFIG_ESP_WIFI_FTM_RESPONDER_SUPPORT` | `y` by default, **but depends on `ESP_WIFI_FTM_ENABLE`** |
| Board USB | Built-in USB-Serial-JTAG, VID `303A` / PID `1001` |
| Console config required | `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` |

**FTM-disabled trap** (measured in Phase 0, correcting an earlier reading of
this table). The initiator and responder options really are `default y`, which
made them look like they need no configuration — but both `depends on
ESP_WIFI_FTM_ENABLE`, and that option is `default n`
(`components/esp_wifi/Kconfig:397` in ESP-IDF v5.5.2). A project that does not
set it gets **no FTM at all**:

```
# CONFIG_ESP_WIFI_FTM_ENABLE is not set     <- generated sdkconfig, no defaults
```

The earlier measurements in this document were taken with the Espressif FTM
example, whose own `sdkconfig.defaults` sets it — which is why the dependency
never surfaced. Every firmware in this repo must carry:

```
CONFIG_ESP_WIFI_FTM_ENABLE=y
CONFIG_ESP_WIFI_FTM_INITIATOR_SUPPORT=y
CONFIG_ESP_WIFI_FTM_RESPONDER_SUPPORT=y
```

Caught by the on-target L2 test (`tests/target_smoke/`), which asserts the
symbols are defined rather than assuming it:

```
./main/target_smoke_main.c:46:test_ftm_is_supported_by_this_soc:FAIL:
    CONFIG_ESP_WIFI_FTM_INITIATOR_SUPPORT is disabled
```

**Console trap.** The example defaults to `CONFIG_ESP_CONSOLE_UART_DEFAULT`,
putting the REPL on UART0 whose pins are not wired to USB. Symptom is
misleading: boot logs *do* appear on the COM port (secondary console), but every
write to the prompt fails with a serial write timeout because the firmware never
reads that endpoint.

## 2. FTM session behaviour

| Fact | Value |
| --- | --- |
| Session duration | **~1.5 s** at `frm_count=32`, `burst_period=2` |
| Effective sample rate | **~0.6 Hz** |
| Session structure | non-ASAP, 8 bursts, 4 FTM/burst, 200 ms period, 32 ms burst duration |
| Healthy valid-reading count | **28–30 of 30** |
| Full-band scan cost | **~2.5 s** — unusable inside a measurement loop |
| Association required? | **No.** Initiator logs `Haven't to connect to a suitable AP now!` and the session proceeds normally |

**Design consequence:** cache BSSID + channel once; never scan per measurement.
Unassociated FTM is the correct default — it avoids reconnect churn.

## 3. Distance quantisation

`rtt_est` is truncated to **whole nanoseconds**, and `c/2 × 1 ns = 15.0 cm`.
Every `dist_est` reading observed is an exact multiple of **0.15 m**.

Sub-nanosecond precision **is** available — the driver logs
`Avg raw RTT: 8.489 nSec` — and is exposed as `rtt_raw` in
`wifi_event_ftm_report_t`.

**Design consequence:** log and calibrate against **`rtt_raw`**, not `dist_est`.
`dist_est` is for display only.

## 4. Zero-distance clamp

`dist_est` is `uint32_t` (centimetres, unsigned). Once raw RTT minus the
internal calibration goes negative, the result **saturates at 0**, it does not
go negative.

With the boards side by side (RSSI −28 dBm), **every** session reported
`Avg raw RTT: 0.0 nSec` and `0.00 meters` while still reporting success.

**Design consequences:**
- Calibration cannot be performed at zero distance.
- Any host-side offset arithmetic must treat the value as **signed**;
  over-correcting an unsigned value wraps to ~4 billion.

## 5. Responder T1 offset — linear, with inverted sign

`esp_wifi_ftm_resp_set_offset(int16_t offset_cm)` adds an offset to T1 (time of
departure at the responder). Since `RTT = (T4−T1) − (T3−T2)`, a **positive**
offset **reduces** reported distance.

**Rule: `reported ≈ true − offset`.**

Measured sweep, 4 sessions each, fixed physical setup:

| `--offset=` | Readings (m) | Mean | Shift vs. baseline | Expected |
| --- | --- | --- | --- | --- |
| `0` | 1.35, 1.05, 1.20, 1.20 | 1.20 | — | — |
| `-200` | 4.20, 2.85, 2.85, 2.85 | 3.19 | **+1.99 m** | +2.00 |
| `-400` | 4.80, 5.10, 5.25, 5.10 | 5.06 | **+3.86 m** | +4.00 |
| `600` | 0.00 ×4 | 0.00 | clamped | — |

The control is linear and accurate to within ~0.14 m over a 4 m span.

> Note the CLI parsing detail: use the long form `--offset=-200`. With the short
> form, argtable3 may parse `-200` as a flag rather than a value.

## 6. Valid-reading count is the quality signal

The clamped `+600` case **still reported session success** while the valid count
collapsed from 30/30 to **2–3 of 30**.

**Design consequence:** firmware must log `valid/total`; the host must treat a
low ratio as *invalid*, not as a genuine 0.00 m reading. Status alone is not
sufficient to detect a bad measurement.

## 7. Baseline at ~1.2 m separation

10 sessions across two runs, no offset applied, 28–30/30 valid:

```
1.35  1.05  1.20  1.20  1.20  1.20  1.65  0.75  1.65  0.90   (metres)
mean 1.22 m,  spread 0.75–1.65 m,  RSSI −49…−62 dBm
```

## 8. Slow drift — the dominant practical problem

**This is the most important finding for system design.**

An attempt to A/B whether explicitly issuing `ftm -R -o 0` differs from never
issuing it was **confounded and is inconclusive**. Within a single run at a
fixed physical setup:

| Block | Mean distance | Raw RTT range | RSSI |
| --- | --- | --- | --- |
| First 6 sessions | 1.23 m | 5.2–11.9 ns | −52…−62 |
| Next 6 sessions | 0.10 m | 0.0–4.1 ns | −48…−51 |

An earlier run issuing the identical command produced 1.20 m. The shift is
therefore **not** attributable to the offset command — it is **drift on a
timescale of tens of seconds**, with RSSI moving simultaneously.

**Design consequences:**
- A handful of sessions **cannot** calibrate this system.
- Every calibration point needs **minutes** of continuous logging.
- RSSI and valid-count must be logged alongside every sample so drifting
  periods can be identified and excluded.
- Filtering (rolling median) is mandatory, not cosmetic.
- Any test asserting an absolute distance must use a **tolerance band and a
  sample count**, never a single reading.

## 10. Standing test fixture — boards fixed at 1.00 m

**The two boards are physically fixed 1.00 m apart** for development. This is a
permanent bench fixture, not a temporary arrangement.

Consequences:

- **Autonomous tests may assert against a 1.00 m ground truth** without an
  operator present. This is what makes L3 E2E distance assertions possible at
  all.
- Any test asserting distance must still use a **tolerance band and a minimum
  sample count** — at this exact separation the measured spread was
  0.75–1.65 m (§7) and drift is real (§8). A tight assertion will flake.
- Suggested E2E band: mean over ≥ 60 samples, expected 1.00 m, tolerance ±0.75 m,
  valid ratio ≥ 0.8. Tighten only with measured justification.
- If an agent finds readings consistently far outside this band, the likely
  causes in order are: boards moved, clamp condition (§4, §6), wrong calibration
  offset (§5), or drift (§8) — **not** a broken algorithm. Check the fixture
  first.

## 9. Defects in the Espressif example

Relevant when reusing its code as reference.

| Defect | Location | Impact |
| --- | --- | --- |
| Report leaked on failure path — `esp_wifi_ftm_get_report()` only called on success | `main/ftm_main.c:641-653` | Slow leak in a continuous loop, where failures are routine |
| `rtt_raw` discarded, only `rtt_est` logged | `wifi_cmd_ftm` | Loses sub-ns precision needed for calibration |
| Per-frame report logging off by default (`ESP_FTM_REPORT_LOG_ENABLE=n`) | `Kconfig.projbuild` | `g_report_lvl == 0`, per-frame RTT/T1–T4/RSSI silently discarded |
| `find_ftm_responder_ap()` returns pointer into `g_ap_list_buffer`, freed by next scan | `main/ftm_main.c` | Dangling pointer; safe only because caller consumes immediately |
| Shared state unsynchronised across WiFi event task / console task | `s_rtt_est`, `s_dist_est`, `s_ftm_report_num_entries` | Race, benign in practice |

**Non-defect (checked):** `ap <ssid>` with no password does **not** crash;
argtable3 returns `""`, not `NULL`. An earlier suspicion of a NULL-deref at
`ftm_main.c:463` was tested on hardware and disproved.
