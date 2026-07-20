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
4. Phase 0 was unavailable during the original implementation, then was merged
   before review. Rebasing onto `main` at `ed31100` exposed one integration
   regression: `dev.ps1 build` still targeted the now-empty repository root.
   The runner now builds the canonical `tools/bench_firmware` project, with a
   regression test that verifies the configured project exists.

## Scope changes

- Added a minimal `tools/bench/__init__.py` so the scripts can be imported by
  pytest without copying implementation code.
- Added `two_board.py --transcript` to save the bounded initiator transcript
  directly. This was needed to commit auditable real-data fixtures without
  treating terminal output as a recording.
- No product firmware, `components/`, or Docker files were changed. After the
  Phase 0 merge, `tools/dev.sh`, its PowerShell help, and `docs/CONTAINER.md`
  were updated only to route the existing `build` command to the moved bench
  project. `tests/tools/test_dev_build_target.py` protects that integration.
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

The branch was rebased onto Phase 0-complete `main` (`ed31100`) and every
available automated level was run again.

### Container firmware build

Command:

```powershell
.\tools\dev.ps1 build
```

The first post-rebase run correctly exposed the stale root-project path:

```text
== Firmware build (esp32c3) -> /project/build_container/firmware
CMakeLists.txt not found in project directory /project
```

After routing the runner to `tools/bench_firmware`, the final clean rerun
completed in 71.9 s:

```text
== Bench firmware build (esp32c3) -> /project/build_container/firmware
Running cmake in directory /project/build_container/firmware
Building ESP-IDF components for target esp32c3
ftm_measurement.bin binary size 0xcaaa0 bytes. Smallest app partition is 0x100000 bytes. 0x35560 bytes (21%) free.
Project build complete.
```

### L1a — Ceedling host domain tests

Command (runs L1a then L1b):

```powershell
.\tools\dev.ps1 test-host
```

Final rerun output (L1a portion, 10.83 s):

```text
✅ OVERALL TEST SUMMARY
TESTED:  15
PASSED:  15
FAILED:   0
IGNORED:  0
```

### L1b — ESP-IDF Linux-target host tests

Final output from the same command:

```text
14 Tests 0 Failures 0 Ignored
OK
=== L1b finished: 0 failure(s) ===
== L1a + L1b PASS
```

The deliberate failure-path integrity check also passed:

```powershell
.\tools\dev.ps1 test-host-selfcheck
```

```text
15 Tests 1 Failures 0 Ignored
FAIL
== self-check OK: failing test -> exit code 1, no hang
```

### Coverage

Command:

```powershell
.\tools\dev.ps1 coverage
```

Verbatim summary (19.6 s):

```text
lines: 100.0% (19 out of 19)
functions: 100.0% (2 out of 2)
branches: 91.7% (11 out of 12)
== coverage report OK: 19 lines measured
```

### L2 — on-target Unity

Build command:

```powershell
.\tools\dev.ps1 target-build
```

Verbatim summary (83.6 s):

```text
Successfully created esp32c3 image.
ftm_target_smoke.bin binary size 0xb8390 bytes. Smallest app partition is 0x100000 bytes. 0x47c70 bytes (28%) free.
Project build complete.
```

The L3 run below flashed this app to both boards and asserted each board's
`FTM_TARGET_SMOKE_PASS failures=0` marker.

### L3 — physical-board validation

Command:

```powershell
.\tools\dev.ps1 e2e
```

Verbatim output (32.88 s pytest time, 43.5 s command time):

```text
tests\e2e\test_harness_smoke.py::test_both_boards_boot_the_app PASSED    [ 33%]
tests\e2e\test_harness_smoke.py::test_both_boards_pass_their_on_target_tests PASSED [ 66%]
tests\e2e\test_harness_smoke.py::test_roles_are_bound_to_the_expected_boards PASSED [100%]
======================= 3 passed, 3 warnings in 32.88s ========================
```

The original Phase 1 hardware evidence remains:

- normal assigned roles: **PASS**, 8 sessions, 235 per-frame samples, 27.2 s;
- physically touching clamp: **expected FAIL**, exit 1 with the required hint,
  4 sessions, 120 per-frame samples, 20.7 s.

Those verbatim outputs are in acceptance criteria 2 and 3.

### L4 — Python host tools

Command:

```powershell
.\tools\dev.ps1 tools-test
```

Verbatim output:

```text
collected 28 items
tests\tools\test_dev_build_target.py::test_container_build_targets_the_moved_bench_firmware PASSED [ 42%]
======================= 28 passed, 28 warnings in 0.19s =======================
```

The warnings are pytest-embedded's experimental `record_xml_attribute` hook;
there were no test failures.

### Lsim and L5

Their directories are present but intentionally empty until later phases, as
documented in their READMEs. There were no Lsim or L5 tests to execute.

### Post-rebase Phase 1 validator recheck

The container-built bench image was flashed through Phase 0's MAC-based runner
to both boards, proving the two phases integrate:

```text
role 'responder' -> COM3
MAC: 14:63:93:8d:98:74
Hash of data verified.
flashed 'responder' on COM3
role 'initiator' -> COM4
MAC: 14:63:93:8d:96:e4
Hash of data verified.
flashed 'initiator' on COM4
```

The immediate eight-session recheck at the fixed 1.00 m fixture exited 1
because the hardware was in the already-documented all-zero drift/clamp state:

```text
COM3: 14:63:93:8d:98:74
COM4: 14:63:93:8d:96:e4
FAIL COM3 responder + COM4 initiator: 8 sessions, 224 per-frame RTT samples
  ERROR: all sessions reported zero raw RTT
  ERROR: boards too close? all reported distances are 0.00 m (FTM clamp condition)
FAIL: board validation failed
```

This does not contradict the committed normal-spacing PASS fixture or
`HARDWARE_FINDINGS.md` §8: the validator correctly rejected the live clamped
measurement instead of producing a false PASS.

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

### Original full-suite integration gap (resolved)

Phase 0 ran in parallel as requested. Its worktree had uncommitted scaffolding,
so consuming it would have raced another agent and violated worktree isolation.
After Phase 0 merged, this branch was rebased onto `ed31100` and the complete
available suite was run; results are recorded above.

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

1. The post-rebase live eight-session check at 1.00 m was all-zero/clamped.
   Repeat later to observe whether the documented slow drift returns to the
   non-zero region; do not weaken the validator to accommodate it.
2. Per-board fingerprints currently describe one assigned-role pair. A future
   fleet with an independent known-good reference can isolate initiator and
   responder degradation more precisely.
