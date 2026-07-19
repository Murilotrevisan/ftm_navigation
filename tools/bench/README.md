# FTM bench host tools

These scripts drive the preserved Espressif console firmware in
`tools/bench_firmware`. Run Python commands inside the project venv. Firmware
builds are verified in the `ftm-dev` container; flashing and serial access run
on Windows.

## Autonomous validation

The default project roles are COM3 responder and COM4 initiator:

```powershell
.\.venv\Scripts\python.exe tools\bench\validate_board.py `
    --first-port COM3 --second-port COM4 --sessions 8 `
    --log-dir bench_logs
```

The validator reads each MAC with esptool, flashes both boards through
`idf.ps1`, opens both serial ports for the lifetime of the run, executes the
sessions, and exits 0 only when all checks pass. Use `--skip-flash` only when the
same bench image is already present. `--first-port` is always the responder and
`--second-port` the initiator.

At least eight normal 32-frame sessions are needed to obtain the 200 real
per-frame samples required for a fingerprint. The first passing run writes one
JSON baseline per MAC under `fingerprints/`; later runs compare against it and
warn rather than overwriting it. Both records describe the assigned-role pair,
so keep the role and peer MAC fields when interpreting a warning.

Raw logs supplied with `--log-dir` are UTF-8 with replacement for damaged serial
bytes. Keep them when diagnosing a failure. The committed pytest fixtures under
`tests/tools/fixtures/bench` are recordings from these physical boards, not
synthesised console text.

## Manual diagnostics

Drive one board and preserve its transcript:

```powershell
.\.venv\Scripts\python.exe tools\bench\console.py `
    --port COM3 --log bench_logs\COM3.log
```

Drive a responder and initiator from the same process:

```powershell
.\.venv\Scripts\python.exe tools\bench\two_board.py `
    --responder-port COM3 --initiator-port COM4 --sessions 8 `
    --log-dir bench_logs
```

Holding both ports open is essential: opening a port resets its board, so
separate sequential console processes lose the responder AP between steps.

For a controlled clamp diagnostic, the responder offset must use the long form
internally because negative values can be misread as options:

```powershell
.\.venv\Scripts\python.exe tools\bench\two_board.py `
    --responder-port COM3 --initiator-port COM4 --sessions 4 `
    --responder-offset 600 --ssid FTM_CLAMP --log-dir bench_logs\clamp
```

An all-zero result usually means clamp/drift or boards placed too close, not a
failed radio. Restore the responder offset by resetting the board before normal
validation.

## ESP-IDF wrapper

`idf.ps1` prepends the installed IDF Python directory to `PATH`, activates
ESP-IDF v5.5.2, then forwards every remaining argument to `idf.py`:

```powershell
.\tools\bench\idf.ps1 -C tools\bench_firmware -p COM3 flash
```

Do not install packages into that IDF Python. Host test dependencies belong only
in `.venv`.
