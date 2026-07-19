# Phase 1 — Bench Validation Firmware

| | |
| --- | --- |
| **Status** | Not started |
| **Depends on** | Nothing. May run in parallel with Phase 0. |
| **Blocks** | Phase 2 |
| **Read first** | `docs/PLAN.md` (all), `docs/HARDWARE_FINDINGS.md` (all), `docs/WORKFLOW.md` (all) |

---

## Objective

Preserve the working Espressif FTM console example as a **board bring-up and
validation tool** under `tools/`, plus the host scripts that drive it.

**Decision confirmed by the reviewer: keep the console example.** It stays as a
known-good hardware reference for manual probing, under `tools/`.

**This is deliberately a small phase.** The example already works and is already
verified on both boards. Do not redesign it. Its job is to answer one question
quickly: *"is this board's FTM hardware working?"*

## Why this exists

When a new board joins the fleet, or when the definitive firmware misbehaves,
you need a known-good reference to isolate hardware from software. The console
example is that reference — it is Espressif's own code, and it has been
end-to-end verified on this exact hardware (see `docs/HARDWARE_FINDINGS.md`).

It is explicitly **exempt from the layered architecture** in
`docs/ARCHITECTURE.md`. It is a tool, not product firmware.

## Current state

The example is at `main/ftm_main.c` with `sdkconfig.defaults`, and **works**:

- Builds for `esp32c3`, ~0xd0860 bytes.
- Flashes and runs on COM3 and COM4.
- `scan`, `ap`, `sta`, `query`, `ftm -I`, `ftm -R` all verified working.
- One change already applied to `sdkconfig.defaults`:
  `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` — **required**, see
  `docs/HARDWARE_FINDINGS.md` §1.

## Deliverables

```
tools/bench_firmware/
├── CMakeLists.txt
├── sdkconfig.defaults          # incl. CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y
├── main/
│   ├── CMakeLists.txt
│   ├── ftm_main.c              # the example, moved
│   ├── idf_component.yml
│   └── Kconfig.projbuild
└── README.md                   # validation procedure

tools/bench/
├── idf.ps1                     # ESP-IDF env wrapper (PATH fix + export)
├── console.py                  # drive one board's REPL, log to file
├── two_board.py                # drive COM3 + COM4 from one process
├── validate_board.py           # automated pass/fail board check
└── README.md
```

The repository root `main/` is then freed for the Phase 3 firmware.

## Tasks

1. **Move**, do not rewrite, the example into `tools/bench_firmware/`. Keep the
   Espressif licence header and provenance note.
2. Enable **FTM report logging** in its `sdkconfig.defaults`
   (`CONFIG_ESP_FTM_REPORT_LOG_ENABLE=y` plus the SHOW_* options). It is off by
   default, which silently discards per-frame RTT/T1–T4/RSSI — exactly the data
   you want when diagnosing a suspect board. See `HARDWARE_FINDINGS.md` §9.
3. **Fix the report leak** on the failure path (`ftm_main.c:641-653` in the
   original): `esp_wifi_ftm_get_report()` must be called on failure and timeout
   too, not only on success. This is the one code change worth making — the
   validation script runs many sessions in a row.
   - Keep the change minimal and comment it as a deviation from upstream.
4. **Port the host scripts.** Working versions were used during evaluation:
   - `idf.ps1` — prepends IDF python to PATH, runs `export.ps1`, invokes
     `idf.py`. Required because shell state does not persist and `export.ps1`
     fails without the PATH fix (`docs/PLAN.md` §6).
   - `two_board.py` — opens **both** ports in one process so the responder stays
     up while the initiator measures. Opening a port resets the board, so
     sequential single-port scripts cannot keep an AP alive across steps. This
     is the key lesson from the evaluation; do not regress it.
5. **`validate_board.py`** — the actual deliverable. Automated, pass/fail:
   - Flash bench firmware to both boards.
   - Bring up responder on one, run N sessions from the other.
   - Assert: session success, `valid/total >= 0.8`, non-zero `rtt_raw` on at
     least some sessions, plausible RSSI.
   - Print a clear PASS/FAIL summary and exit non-zero on failure.

## Required tests

Lighter than product code, but not absent:

- `validate_board.py` gets pytest coverage of its **parsing and decision logic**
  with recorded serial transcripts as fixtures (capture real output; do not
  invent it). Cover:
  - All sessions succeed → PASS.
  - Low valid ratio (e.g. 2/30, the clamp signature) → FAIL, see
    `HARDWARE_FINDINGS.md` §6.
  - All-zero distance → FAIL with the "boards too close?" hint
    (`HARDWARE_FINDINGS.md` §4).
  - Garbled/partial serial line → handled, no crash.
  - Board never reaches prompt → clear timeout message, not a hang.
- `two_board.py` line-splitting: partial lines across reads, CRLF, UTF-8
  replacement.

## Acceptance criteria

- [ ] `tools/bench_firmware` builds and flashes to both COM3 and COM4.
- [ ] `validate_board.py` runs autonomously and reports PASS on both boards.
- [ ] It reports **FAIL with a useful message** when the boards are placed
      touching (clamp condition) — verify this by actually doing it.
- [ ] Report leak fix present and commented.
- [ ] `tools/bench_firmware/README.md` documents the validation procedure for a
      new board, start to finish.
- [ ] Root `main/` no longer contains the example.

## Traps

- **Board resets when the serial port is opened.** Any script that opens a port
  per step will restart the board and lose AP state. Use one process holding
  both ports.
- **`ftm -R -o <n>` short form**: argtable3 may parse a negative value as a
  flag. Use `--offset=-200`.
- Readings of `0.00 m` usually mean the boards are **too close**, not broken.

## Board fingerprinting

`validate_board.py` records a **baseline fingerprint per board**: mean and σ of
`rtt_raw_ns` over ≥ 200 samples at the fixed 1.00 m reference
(`HARDWARE_FINDINGS.md` §10), stored as
`tools/bench/fingerprints/<mac>.json` and committed.

On later runs it compares against the stored fingerprint and warns on
significant divergence. This is the only way to distinguish "this board has
degraded" from "the environment changed today" — without a stored baseline,
a drifting board is indistinguishable from the drift already documented in
findings §8.

The fixed 1.00 m jig is what makes this possible; it would not be meaningful
without a repeatable reference distance.
