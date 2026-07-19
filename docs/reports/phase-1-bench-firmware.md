# Report — phase-1/bench-firmware

## What was built

The verified ESP-IDF v5.5.2 FTM console example was moved from the repository
root into `tools/bench_firmware`. Detailed per-frame FTM reporting and the
USB-Serial-JTAG console are enabled by default. The upstream report ownership
leak is fixed on both failure and timeout paths.

The Windows host tools under `tools/bench` now provide:

- an ESP-IDF environment wrapper;
- one-port logging with bounded prompt waits;
- one-process, two-port FTM session control;
- autonomous assigned-role validation for COM3 responder and COM4 initiator;
- parsing and pass/fail decisions for session count, valid ratio, raw RTT,
  RSSI, and the zero-distance clamp;
- one recorded baseline fingerprint per board MAC; and
- recorded passing, low-valid, all-zero, partial-line, and timeout test coverage.

## Deviations from the phase document

1. The original project had no persistent target selection and a clean build
   silently selected ESP32. `CMakeLists.txt` now defaults to `esp32c3` while
   allowing an explicit override. The first wrong-target build was discarded
   and is not reported as acceptance evidence.
2. Fingerprints are stored per MAC with explicit `role` and `peer_mac` fields,
   but both baseline files describe the same assigned-role pair. Reversing the
   two boards produced a 1.00 m clamp during evaluation, so reverse-role data
   was not misrepresented as a passing baseline.
3. `idf.ps1 ... flash` performs ESP-IDF's normal host-side incremental build as
   part of flashing. A separate authoritative build was run in `ftm-dev`; this
   is the tension between the phase's required pre-Phase-0 wrapper and the
   project-wide container-build rule.
4. The Phase 0 L1/L2/L3 pytest scaffolding was not available on this branch.
   Phase 0 was running in parallel and its worktree still contained uncommitted
   files. The complete test tree that exists on this branch was run, but the
   later integration suite remains a merge-gate item.

## Scope changes

- Added a minimal `tools/bench/__init__.py` so the scripts can be imported by
  pytest without copying implementation code.
- Added `two_board.py --transcript` to save the bounded initiator transcript
  directly. This was needed to commit auditable real-data fixtures without
  treating terminal output as a recording.
- No product firmware, `components/`, Docker, or Phase 0 scaffolding was added
  or changed.
- The generated `sdkconfig`, dependency lock, host/container build trees, and
  Python caches were removed before commit.

## Evidence per acceptance criterion

### 1. `tools/bench_firmware` builds and flashes to both COM3 and COM4

Container build command:

```powershell
docker run --rm -v "${PWD}:/project" -w /project/tools/bench_firmware ftm-dev idf.py -B build_container build
```

Verbatim final incremental output:

```text
Executing action: all (aliases: build)
Running ninja in directory /project/tools/bench_firmware/build_container
Executing "ninja all"...
[1/4] cd /project/tools/bench_firmware/build_container/esp-idf/esptool_py && /opt/esp/python_env/idf5.5_py3.12_env/bin/python /opt/esp/idf/components/partition_table/check_sizes.py --offset 0x8000 partition --type app /project/tools/bench_firmware/build_container/partition_table/partition-table.bin /project/tools/bench_firmware/build_container/ftm_measurement.bin
ftm_measurement.bin binary size 0xcaaa0 bytes. Smallest app partition is 0x100000 bytes. 0x35560 bytes (21%) free.
[2/4] Performing build step for 'bootloader'
[1/1] cd /project/tools/bench_firmware/build_container/bootloader/esp-idf/esptool_py && /opt/esp/python_env/idf5.5_py3.12_env/bin/python /opt/esp/idf/components/partition_table/check_sizes.py --offset 0x8000 bootloader 0x0 /project/tools/bench_firmware/build_container/bootloader/bootloader.bin
Bootloader binary size 0x52b0 bytes. 0x2d50 bytes (35%) free.
[3/4] No install step for 'bootloader'
[4/4] Completed 'bootloader'

Project build complete. To flash, run:
 idf.py flash
or
 idf.py -p PORT flash
or
 python -m esptool --chip esp32c3 -b 460800 --before default_reset --after hard_reset write_flash --flash_mode dio --flash_size 2MB --flash_freq 80m 0x0 build_container/bootloader/bootloader.bin 0x8000 build_container/partition_table/partition-table.bin 0x10000 build_container/ftm_measurement.bin
```

Flash commands (the validator uses this same wrapper for each port):

```powershell
.\tools\bench\idf.ps1 -C tools\bench_firmware -B tools\bench_firmware\build_host -p COM3 flash
.\tools\bench\idf.ps1 -C tools\bench_firmware -B tools\bench_firmware\build_host -p COM4 flash
```

Verbatim flash evidence across the two assigned-port runs:

```text
esptool.py --chip esp32c3 -p COM3 -b 460800 ...
Serial port COM3
Chip is ESP32-C3 (QFN32) (revision v0.4)
USB mode: USB-Serial/JTAG
MAC: 14:63:93:8d:98:74
Hash of data verified.
Leaving...
Hard resetting via RTS pin...
Done

esptool.py --chip esp32c3 -p COM4 -b 460800 ...
Serial port COM4
Chip is ESP32-C3 (QFN32) (revision v0.4)
USB mode: USB-Serial/JTAG
MAC: 14:63:93:8d:96:e4
Hash of data verified.
Leaving...
Hard resetting via RTS pin...
Done
```

Criterion: **met**.

### 2. `validate_board.py` autonomously reports PASS on both boards

Command:

```powershell
.\.venv\Scripts\python.exe tools\bench\validate_board.py --skip-flash --sessions 8 --log-dir tests\tools\fixtures\bench\pass_capture
```

Verbatim output (27.2 s wall time):

```text
COM3: 14:63:93:8d:98:74
COM4: 14:63:93:8d:96:e4
PASS COM3 responder + COM4 initiator: 8 sessions, 235 per-frame RTT samples
  recorded baseline fingerprint C:\Users\murilo\Documents\Projetos\FTM_measurement\ftm-phase-1\tools\bench\fingerprints\14-63-93-8d-98-74.json
  recorded baseline fingerprint C:\Users\murilo\Documents\Projetos\FTM_measurement\ftm-phase-1\tools\bench\fingerprints\14-63-93-8d-96-e4.json
PASS: both boards validated in their assigned roles
```

Criterion: **met**.

### 3. Touching boards produce FAIL with a useful clamp message

The operator physically placed the two boards touching before this command.

Command:

```powershell
.\.venv\Scripts\python.exe tools\bench\validate_board.py --skip-flash --sessions 4
```

Verbatim output and exit status (20.7 s wall time, exit 1 as required):

```text
COM3: 14:63:93:8d:98:74
COM4: 14:63:93:8d:96:e4
FAIL COM3 responder + COM4 initiator: 4 sessions, 120 per-frame RTT samples
  ERROR: all sessions reported zero raw RTT
  ERROR: boards too close? all reported distances are 0.00 m (FTM clamp condition)
FAIL: board validation failed
```

Criterion: **met**.

### 4. Report leak fix is present and commented

Command:

```powershell
rg -n -C 2 "Upstream deviation|esp_wifi_ftm_get_report\(NULL, 0\)" tools\bench_firmware\main\ftm_main.c
```

Verbatim relevant output:

```text
649-        /* FTM Failure case */
650-        ESP_LOGE(TAG_STA, "FTM procedure failed!");
651:        /* Upstream deviation: release the driver-owned report on failure too. */
652:        esp_wifi_ftm_get_report(NULL, 0);
653-    } else {
654-        /* Timeout, end session gracefully */
655-        ESP_LOGE(TAG_STA, "FTM procedure timed out!");
656-        esp_wifi_ftm_end_session();
657:        /* Upstream deviation: release the driver-owned report on timeout too. */
658:        esp_wifi_ftm_get_report(NULL, 0);
```

The ESP32-C3 container build in criterion 1 compiled these calls.

Criterion: **met**.

### 5. Firmware README documents new-board validation start to finish

Command:

```powershell
Select-String -LiteralPath tools\bench_firmware\README.md -Pattern '^## Validate a new board from start to finish','validate_board.py','fingerprints/<mac>.json'
```

Verbatim output:

```text
tools\bench_firmware\README.md:9:## Validate a new board from start to finish
tools\bench_firmware\README.md:22:.\.venv\Scripts\python.exe tools\bench\validate_board.py `
tools\bench_firmware\README.md:33:and creates or compares `tools/bench/fingerprints/<mac>.json`. Review every
```

Criterion: **met**.

### 6. Root `main/` no longer contains the example

Command:

```powershell
Write-Output ("root main/ftm_main.c exists: {0}" -f (Test-Path -LiteralPath 'main\ftm_main.c'))
Write-Output ("bench firmware ftm_main.c exists: {0}" -f (Test-Path -LiteralPath 'tools\bench_firmware\main\ftm_main.c'))
```

Verbatim output:

```text
root main/ftm_main.c exists: False
bench firmware ftm_main.c exists: True
```

Criterion: **met**.

## Test results

### L1a — Ceedling host domain tests

**Skipped.** Phase 0 was still running in parallel and no Ceedling suite exists
in this branch. Verified before reporting:

```text
## phase-0/test-infra
?? components/
?? docker/docker-compose.yml
?? tests/
?? tools/
```

### L1b — ESP-IDF Linux-target host tests

**Skipped for the same reason:** the Phase 0 harness was not committed or
available on `main`.

### L2 — on-target Unity

**Skipped:** no Phase 0 target-test app exists on this branch.

### L3 — physical-board validation

The Phase 1 autonomous validator was run directly because the Phase 0
pytest-embedded harness was not yet available. Results:

- normal assigned roles: **PASS**, 8 sessions, 235 per-frame samples, 27.2 s;
- physically touching clamp: **expected FAIL**, exit 1 with the required hint,
  4 sessions, 120 per-frame samples, 20.7 s.

The verbatim outputs are in acceptance criteria 2 and 3.

### L4 — Python host tools

Command:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests
```

Verbatim output:

```text
...........                                                              [100%]
11 passed in 0.07s
```

The full test tree present on this branch is **11 passed, 0 failed**. Plugin
autoload and the cache provider were disabled to isolate the L4 tool suite;
this does not skip any test collected from `tests/`.

### Lsim and L5

Not applicable to Phase 1 and not present on this branch.

## Blockers encountered

### COM3 never reached the prompt on the first validator run

Observed output:

```text
FAIL: COM3: board never reached the 'ftm>' prompt within 15.0s; check that USB-Serial-JTAG console support is enabled
```

Diagnostics confirmed the firmware configuration:

```text
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED=y
```

A five-second plain-pyserial read returned `''`. After explicitly deasserting
DTR and RTS immediately after open, the same read produced the complete ESP32-C3
boot log and `ftm>` prompt. The root cause was pyserial's initial control-line
state holding USB-Serial-JTAG reset, not missing console configuration.

### Full cross-level integration suite unavailable

Phase 0 ran in parallel as requested. Its worktree had uncommitted scaffolding,
so consuming it would have raced another agent and violated worktree isolation.
This remains an integration merge-gate item, not a hidden pass.

### Shared-board contention with the parallel Phase 0 run

After the deliberate touching-board check, the operator restored the fixture
to 1.00 m. A final repeat was attempted, but the parallel Phase 0 process was
also using the same physical boards. Captured boot logs proved that Phase 0's
`ftm_target_smoke` image replaced the Phase 1 firmware on COM3, and a later
attempt found COM4 legitimately busy. This is shared-hardware contention, not
a Phase 1 firmware failure. The earlier normal-spacing eight-session PASS is
the acceptance recording committed under `tests/tools/fixtures/bench`.

During that diagnosis, a separate host-wrapper defect was found: PowerShell
advanced parameter binding did not reliably forward `-p COM3`, allowing the
build directory's cached COM4 port to be reused. `idf.ps1` now binds `-C`,
`-B`, and `-p` explicitly before invoking `idf.py`. A post-fix flash log shows
`esptool.py --chip esp32c3 -p COM3`, COM3's expected MAC, verified hashes, and
a clean hard reset.

## New findings

- Board A's base MAC was confirmed as `14:63:93:8d:98:74`; its SoftAP BSSID in
  every recording is `14:63:93:8d:98:75`.
- Pyserial must set both DTR and RTS false after opening these USB-Serial-JTAG
  ports or a board can remain silent in reset.
- At the fixed 1.00 m fixture, the normal assigned-role pair first drifted into
  an all-zero clamp and later passed with non-zero raw RTT. This is consistent
  with the slow drift already documented in `HARDWARE_FINDINGS.md` §8, so that
  normative document was not changed.
- Reversing the assigned roles also clamped at 1.00 m during this run. The bench
  validator therefore preserves the project's documented board roles.
- A real `+450 cm` responder offset produced successful reports with only
  1–4 valid readings out of 29–30 plus explicit failures. That recording backs
  the low-valid and all-zero decision tests.
- ESP-IDF selects ESP32, not ESP32-C3, for a clean project unless the target is
  set before `project.cmake` initializes it.

## Open items

1. After Phase 0 is committed and merged, rebase this branch again and run its
   L1a, L1b, L2, and pytest-embedded L3 suites before approving a merge.
2. Once Phase 0 releases both serial ports, optionally repeat the normal
   assigned-role validation at the restored 1.00 m fixture. The committed
   acceptance recording already contains the required eight-session PASS.
3. Per-board fingerprints currently describe one assigned-role pair. A future
   fleet with an independent known-good reference can isolate initiator and
   responder degradation more precisely.
