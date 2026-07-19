# Phase 2 — Calibration Firmware + Tkinter Calibrator

| | |
| --- | --- |
| **Status** | Not started |
| **Depends on** | Phase 1 (bench tooling, host scripts) |
| **Blocks** | Phase 3 (needs the calibration table format) |
| **Read first** | `docs/PLAN.md` (all), `docs/HARDWARE_FINDINGS.md` (all), `docs/ARCHITECTURE.md` §6, `docs/WORKFLOW.md` (all), `docs/CONTAINER.md` (all) |

---

## Objective

Produce a **calibration CSV**: for each station (anchor), the offset that makes
its FTM-reported distance match physical reality, measured against the
initiator.

Two parts:
1. **Calibration firmware** — continuous free-running measurement, CSV over USB.
2. **Tkinter calibrator UI** — operator enters the true measured distance, sees
   the FTM estimate live, adjusts the offset, and exports the result.

## Why this is not trivial

Read `docs/HARDWARE_FINDINGS.md` §8 before designing anything. The system
**drifts**: at a fixed physical setup, six consecutive sessions averaged 1.23 m
and the next six averaged 0.10 m. A calibration UI that takes a reading and
computes an offset will produce confident garbage.

**The UI must be built around long averaging, not instant readings.** Minutes
per calibration point, with visible sample count, σ, and valid-ratio so the
operator can see when a point is trustworthy.

## Key facts (do not re-derive)

| Fact | Value | Ref |
| --- | --- | --- |
| Offset sign is **inverted** | `reported ≈ true − offset` | §5 |
| Offset control is linear | −200 cm → +1.99 m; −400 cm → +3.86 m | §5 |
| Offset API type | `int16_t` centimetres | §5 |
| Distance quantised to 15 cm | Calibrate against `rtt_raw`, not `dist_est` | §3 |
| Session rate | ~0.6 Hz (~1.5 s/session) | §2 |
| Healthy valid ratio | 28–30 of 30 | §6 |
| Clamp signature | valid ratio collapses to 2–3/30, status still "success" | §6 |
| Zero-distance clamp | Cannot calibrate at 0 m | §4 |

## Deliverables

```
tools/calibrator/
├── firmware/
│   ├── CMakeLists.txt
│   ├── sdkconfig.defaults           # USB_SERIAL_JTAG console, FTM report log
│   ├── main/
│   │   ├── calib_main.c             # role by Kconfig; free-running loop
│   │   └── Kconfig.projbuild
│   └── README.md
├── ui/
│   ├── calibrator.py                # tkinter entry point
│   ├── serial_reader.py             # background thread -> sample queue
│   ├── model.py                     # pure logic: stats, offset solve (TESTABLE)
│   ├── csv_export.py
│   └── README.md
├── output/                          # generated calibration CSVs
└── tests/
    └── ...                          # pytest, see below
```

## Firmware requirements

- Role by Kconfig (`CALIB_ROLE_INITIATOR` / `CALIB_ROLE_RESPONDER`). This phase
  may use a simple `#ifdef`; the **Strategy pattern is a Phase 3 requirement**,
  not this one.
- **Free-running**: starts measuring at boot, no console command needed.
- Cache BSSID + channel at boot. **Never scan per measurement** — a full scan is
  ~2.5 s (§2).
- **Always drain the report** via `esp_wifi_ftm_get_report()`, including on
  failure and timeout. The upstream example leaks here (§9).
- `esp_log_level_set("*", ESP_LOG_WARN)` so logs do not interleave with data.
- Emit one line per session, prefixed so a parser cannot be confused:

```
FTM,<seq>,<uptime_ms>,<status>,<bssid>,<dist_cm>,<rtt_est_ns>,<rtt_raw_ns>,<rssi_dbm>,<valid>,<total>
```

- **Failed sessions still emit a row** with non-zero status and empty
  measurement fields. Dropouts must be visible in the data, not silently absent.
- Accept a runtime command to set the responder offset (so the UI can sweep
  without reflashing).

## UI requirements

Layout suggestion (not binding):

- **Input:** true measured distance in cm, station label, BSSID (auto-filled
  from the stream).
- **Live display:** current estimate, rolling mean, σ, **sample count**, valid
  ratio, RSSI. Sample count and valid ratio must be prominent — they are how the
  operator knows the point is trustworthy.
- **A live plot** of raw + filtered distance vs. time, so drift is *visible*.
- **Offset control:** set/sweep the responder offset, with the computed
  suggestion. Show the sign convention explicitly in the UI text
  (`reported ≈ true − offset`) — this is an easy and silent thing to get wrong.
- **Guard rails:**
  - Refuse to export a point with fewer than N samples (default: 120 ≈ 3 min).
  - Warn loudly when valid ratio drops below 0.8 (clamp signature).
  - Warn when readings are all 0.00 m — "boards may be too close".
  - Refuse an offset outside `int16_t` range.
- **Export:** append a row to `output/calibration_<date>.csv`.

### CSV schema (contract with Phase 3)

```csv
station_id,bssid,ssid,x_cm,y_cm,z_cm,offset_cm,ref_distance_cm,samples,mean_raw_rtt_ns,stddev_cm,rssi_mean,timestamp
```

Position columns (`x_cm,y_cm,z_cm`) may be blank in this phase — they are filled
in Phase 4 when anchors are physically placed. The columns exist now so the
schema does not change later.

## Required tests

**`model.py` must contain all the logic and no tkinter**, so it is testable
headlessly. The UI file should be a thin shell. This split is the main design
constraint of the phase.

L4 pytest, covering `docs/TESTING.md` §4.1, §4.2, §4.6:

| Case | Expected |
| --- | --- |
| Offset sign | Solving for offset from a known true distance produces the **correct sign**. Test with true > reported and true < reported. |
| Over-correction | Offset that would drive distance negative → explicit error, never a `uint32` wrap |
| Drift detection | Feed the real recorded drift sequence (1.23 m block then 0.10 m block); tool must flag instability, not average them into a confident number |
| Clamp rejection | valid ratio 2/30 with status=success → sample rejected |
| All-zero readings | Flagged as "too close", not exported as offset 0 |
| Insufficient samples | Export refused below threshold |
| Offset out of `int16_t` | Rejected |
| Malformed CSV line from serial | Skipped, counted, no crash |
| Partial line across reads | Reassembled correctly |
| Empty sample window | "No estimate", not 0 |
| Duplicate BSSID export | Rejected or explicit overwrite prompt |

Use **recorded real serial transcripts** as fixtures. Capture them from the
hardware; do not hand-write plausible-looking data.

> **UI placement note.** The tkinter UI is operator-facing and runs on Windows.
> Its **logic lives in `model.py`, which must be tkinter-free** so it is tested
> headlessly inside the container (`docs/CONTAINER.md`). Do not add a headless
> display server to the container to test the widgets — enforce the split
> instead.

## E2E test (L3, autonomous)

`tests/e2e/test_calibration.py`:
- Flash calibrator firmware to the responder and initiator boards, resolved
  **by MAC** (`docs/CONTAINER.md` §5). The boards are fixed **1.00 m apart**
  (findings §10), so the true distance is known without an operator.
- Collect ≥ 60 samples at offset 0; record mean.
- Set offset −200 cm; collect ≥ 60 samples.
- Assert the mean shifted by +2.00 m **within tolerance ±0.5 m** and that valid
  ratio stayed ≥ 0.8.
- Tolerance is wide on purpose: §5 measured +1.99 and +3.86 against expected
  +2.00 and +4.00, and §8 drift is real. A tight assertion here will flake.

## Acceptance criteria

- [ ] Firmware free-runs and emits parseable CSV on both boards.
- [ ] UI shows live estimate, σ, sample count, valid ratio, and a drift plot.
- [ ] UI refuses to export an under-sampled or low-quality point.
- [ ] A full calibration run produces `output/calibration_<date>.csv` matching
      the schema above.
- [ ] All L4 tests pass, including every worst case listed.
- [ ] E2E offset-shift test passes autonomously.
- [ ] `README.md` documents the operator procedure step by step.

## Open questions

- Should the UI drive an **automated offset sweep** (like the evaluation script
  did: 0, −200, −400) and fit a line, rather than relying on a single point?
  This would be more robust against drift. Recommended, but adds scope — flag
  for the reviewer rather than deciding unilaterally.

## Handoff to Phase 3

Report the **exact CSV schema produced** and one real example file. Phase 3's
codegen consumes it and must not have to guess.
