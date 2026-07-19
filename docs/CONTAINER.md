# Container — Build & Unit Test

**Scope: the container builds firmware and runs host unit tests. It does not
touch the boards.**

Flashing and E2E run on Windows, which has the same ESP-IDF v5.5.2. Keeping
hardware access on the host avoids USB passthrough into WSL entirely
(`usbipd-win`, device forwarding, re-attaching after every replug) — complexity
that would buy reproducibility for a step that is already reproducible.

Toolchain versions and validation results are in §8.

| Job | Where | Why |
| --- | --- | --- |
| Firmware build | **Container** | Reproducible toolchain, no host pollution |
| L1 host unit tests (Ceedling) | **Container** | Ruby lives in the image, not on the PC |
| L1b host unit tests (ESP-IDF linux target) | **Container** | Same IDF build system as firmware |
| Coverage (gcovr) | **Container** | Toolchain-coupled |
| Flashing | **Windows host** | Host already has ESP-IDF; no USB forwarding needed |
| L3 E2E, L5 manual | **Windows host, in a venv** | Needs the boards; venv keeps it isolated |
| L4 tool tests | **Windows host, in a venv** | Same venv as E2E |

---

## 1. Runtime

**Docker Desktop 4.82.0**, engine 29.6.1, WSL2 backend (Ubuntu 26.04).
Installed and running on this machine.

## 2. Image

```dockerfile
FROM espressif/idf:v5.5.2
```

**Do not float the tag.** `latest` would silently change the IDF version out
from under the measurements recorded in `docs/HARDWARE_FINDINGS.md`.

### Installed in the image

| Tool | Purpose |
| --- | --- |
| ESP-IDF v5.5.2 + toolchains | Firmware build (base image) |
| ESP-IDF **linux target** support | L1b host tests — verified present in v5.5.2 |
| Unity + CMock | Bundled at `components/unity`, `components/cmock` |
| **Ruby + Ceedling** | L1 host tests. Ruby is in the image, **never on the PC** |
| **gcovr** | Coverage reporting |
| gcc/g++, make, cmake, ninja | Host compilation for Ceedling |

No pytest, no pyserial, no matplotlib — those belong to the host venv (§4).

## 3. Layout

```
docker/
├── Dockerfile              # FROM espressif/idf:v5.5.2 + ruby/ceedling/gcovr
├── docker-compose.yml      # repo volume, ccache volume, UID mapping
├── entrypoint.sh           # sources export.sh (LF line endings!)
└── README.md
tools/
├── dev.ps1                 # Windows entry point
└── dev.sh                  # same, from inside WSL/Linux
```

### Requirements

- **Repo mounted, not copied**, so Windows-side edits are visible immediately.
- **Container build directory must not collide with the host's.** Use
  `build_container/`; a `build/` produced by Windows CMake contains Windows
  absolute paths and fails inside Linux in a confusing way.
- **UID mapping** so generated files are owned by the user, not root.
- **ccache volume** persisted between runs — ESP-IDF builds are slow otherwise.
- **No device mapping. No `--privileged`.** The container has no business
  touching hardware.

## 4. Host venv (E2E, manual, tool tests)

Everything needing the boards runs on Windows inside a project-local venv, so
nothing leaks into the system Python.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-test.txt
```

`requirements-test.txt` pins: `pytest`, `pytest-embedded`,
`pytest-embedded-idf`, `pytest-embedded-serial-esp`, `pyserial`, `matplotlib`,
`numpy`.

`.venv/` is git-ignored. The venv is **required** — do not `pip install` into the
system or IDF Python.

Host-side ESP-IDF still needs its environment activated, and `export.ps1` fails
from a plain shell because the Microsoft Store `python` alias shadows the IDF
Python:

```powershell
$env:Path = "C:\Users\murilo\.espressif\tools\idf-python\3.11.2;" + $env:Path
& "C:\Users\murilo\esp\v5.5.2\esp-idf\export.ps1"
```

## 5. Intended usage

```powershell
# One-time
.\tools\dev.ps1 setup           # build the image
.\tools\dev.ps1 venv            # create .venv and install test deps

# Container: build + host unit tests
.\tools\dev.ps1 build           # firmware build
.\tools\dev.ps1 test-host       # Ceedling + ESP-IDF linux-target unit tests
.\tools\dev.ps1 coverage        # gcovr report -> build_container/coverage/
.\tools\dev.ps1 shell           # interactive shell in the container

# Windows host: hardware
.\tools\dev.ps1 flash responder # flash the responder board
.\tools\dev.ps1 flash initiator # flash the initiator board
.\tools\dev.ps1 e2e             # L3 across both boards (venv)
.\tools\dev.ps1 manual          # L5 operator-driven movement test (venv)
```

`dev.ps1` routes each subcommand to the right place. An agent should never need
to know which side a given command runs on.

## 6. Board identity — do not trust port numbers

Ports re-enumerate unpredictably. **Bind roles to MAC address, not port.**

| Board | MAC | Intended role |
| --- | --- | --- |
| A | *(record during Phase 0)* | Responder / anchor |
| B | `14:63:93:8d:96:e4` | Initiator |

`dev.ps1 flash <role>` must resolve the role to a MAC, probe attached devices,
and flash the right one — **failing loudly if the expected board is absent**.
Flashing the wrong role onto the wrong board produces a system that looks broken
in a very confusing way.

Boards are physically fixed **1.00 m apart** (`HARDWARE_FINDINGS.md` §10).

## 7. Traps

| Symptom | Cause |
| --- | --- |
| **All commands after the first silently do nothing** | **`bash -lc` breaks in this image — use `bash -c`.** The login shell re-sources the IDF export and swallows the rest of the command. Cost an hour to find; do not regress it. |
| **Linux-target test binary never exits** | ESP-IDF's linux target keeps its scheduler running after `UNITY_END()`. Call `exit(failures)` explicitly, or the test hangs forever instead of failing. |
| **gcovr reports 0 lines covered** | `gcovr -r .` does not find Ceedling's gcov data. Point it at `build/gcov/out` (or use Ceedling's own gcov report plugin). A 0 % report looks like a pass — verify it shows real numbers. |
| Build fails with Windows paths in errors | Host `build/` reused in container — use `build_container/` |
| Files created as root on the host | Container UID not mapped |
| Shell script "not found" despite valid path | CRLF line endings — `.gitattributes` forces LF; verify it applied |
| `export.sh` fails / tools missing | Entrypoint did not source `/opt/esp/idf/export.sh` |
| `pip install` hits the system Python | venv not activated (§4) |
| Serial writes time out, boot logs still appear | Firmware missing `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` (`HARDWARE_FINDINGS.md` §1) |
| Responder loses AP state between test steps | Opening a serial port resets the board — hold both ports open for the whole test |

## 8. Validated toolchain

Measured on this machine, not assumed.

### Toolchains inside the container

| Tool | Version | Status |
| --- | --- | --- |
| ESP-IDF | v5.5.2 | OK |
| Ruby | 3.2.3 | OK |
| Ceedling | 1.1.0 | OK |
| gcovr | 7.0 | OK (needs wiring, see below) |
| gcc (host) | 13.3.0 | OK |
| CMock / Unity | bundled in IDF | OK |

### Exercised end to end

| Check | Result |
| --- | --- |
| Firmware build (esp32c3) in container | **PASS** — `0xca6b0` bytes, 21 % free |
| Ceedling `test:all` | **PASS** — 2/2, incl. an out-of-range-enum worst case, 140 ms |
| ESP-IDF linux target build | **PASS** |
| Linux target test binary runs natively | **PASS** — 3/3 |
| gcovr report generation | **PARTIAL** — runs, but reported 0 lines; needs correct object directory |

### Host venv (Windows)

| Item | Result |
| --- | --- |
| `.venv` from IDF Python 3.11.2 | Created |
| pytest | 8.4.2 |
| pytest-embedded (+ idf, serial-esp) | 1.18.2, **multi-DUT `--count` confirmed** |
| pyserial / numpy / matplotlib / construct | 3.5 / 2.4.6 / 3.11.1 / 2.10.70 |
| esptool | 4.12.0 |
| All imports (incl. headless matplotlib) | **PASS** |

gcovr wiring is the one item still to finish, in Phase 0.
